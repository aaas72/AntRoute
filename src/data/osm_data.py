# -*- coding: utf-8 -*-
"""
src/data/osm_data.py

Elâzığ yol ağı (OpenStreetMap) ile ilgili işlemler:
  - download_network       : OSM'den yol ağını indirip GraphML olarak kaydeder
  - load_network           : GraphML dosyasını yükler (seyahat süresi bilgisiyle)
  - snap_to_nodes          : koordinatları en yakın yol düğümüne bağlar
  - compute_cost_matrices  : mesafe (km) ve süre (dk) matrislerini hesaplar
  - route_legs             : rotanın her ayağı için gerçek yol geometrisi ve maliyetleri

Bu modül Streamlit'e bağımlı değildir; önbellekleme arayüz katmanında yapılır.
Sürüş ağı yönlüdür (tek yönlü yollar), bu yüzden matrisler asimetrik olabilir.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import networkx as nx
import numpy as np

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent
GRAPHML_PATH = DATA_DIR / "elazig_osm.graphml"

# Elâzığ şehir merkezi ve indirilecek alanın yarıçapı (Harput dahil)
DEFAULT_CENTER: Tuple[float, float] = (38.6748, 39.2225)
DEFAULT_RADIUS_M = 9000

OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://maps.mail.ru/osm/tools/overpass/api",
)

# OSM'de maxspeed etiketi olmayan yollar için şehir içi varsayılan hızlar (km/sa)
DEFAULT_HWY_SPEEDS = {
    "motorway": 90, "motorway_link": 50,
    "trunk": 70, "trunk_link": 40,
    "primary": 50, "primary_link": 40,
    "secondary": 50, "secondary_link": 35,
    "tertiary": 40, "tertiary_link": 30,
    "unclassified": 30, "residential": 30,
    "living_street": 20, "service": 20, "road": 30,
}
FALLBACK_SPEED_KPH = 30.0

LatLon = Tuple[float, float]


# ---------------------------------------------------------------------- #
# İndirme ve yükleme
# ---------------------------------------------------------------------- #
def _add_travel_times(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    import osmnx as ox

    G = ox.routing.add_edge_speeds(G, hwy_speeds=DEFAULT_HWY_SPEEDS, fallback=FALLBACK_SPEED_KPH)
    G = ox.routing.add_edge_travel_times(G)
    return G


def download_network(
    center: LatLon = DEFAULT_CENTER,
    radius_m: int = DEFAULT_RADIUS_M,
    path: Path = GRAPHML_PATH,
    network_type: str = "drive",
    place: Optional[str] = None,
    retries: int = 3,
    endpoints: Sequence[str] = OVERPASS_ENDPOINTS,
) -> Path:
    """
    Yol ağını OSM'den indirir, hız/süre bilgisi ekler ve GraphML olarak kaydeder.

    `place` verilirse yer adıyla (ör. "Merkez, Elazığ, Türkiye"), aksi halde
    `center` etrafında `radius_m` yarıçaplı alan indirilir. Overpass sunucusu
    meşgulse diğer sunucular üstel bekleme ile denenir.
    """
    import osmnx as ox

    ox.settings.requests_timeout = 300
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        for url in endpoints:
            ox.settings.overpass_url = url
            try:
                logger.info("OSM indiriliyor (%s, deneme %d)...", url, attempt + 1)
                if place:
                    G = ox.graph_from_place(place, network_type=network_type)
                else:
                    G = ox.graph_from_point(center, dist=radius_m, network_type=network_type)
                G = _add_travel_times(G)
                path = Path(path)
                path.parent.mkdir(parents=True, exist_ok=True)
                ox.save_graphml(G, filepath=path)
                logger.info("Kaydedildi: %s (%d düğüm, %d kenar)", path, len(G), G.number_of_edges())
                return path
            except Exception as exc:  # ağ/sunucu hataları
                last_error = exc
                logger.warning("İndirme başarısız (%s): %s", url, str(exc).splitlines()[0][:200])
        time.sleep(5 * 2 ** attempt)
    raise RuntimeError(f"OSM verisi indirilemedi: {last_error}")


def load_network(path: Path = GRAPHML_PATH) -> nx.MultiDiGraph:
    """GraphML dosyasını yükler; seyahat süresi yoksa ekler."""
    import osmnx as ox

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"OSM GraphML bulunamadı: {path}")
    G = ox.load_graphml(path)
    if not all("travel_time" in d for _, _, d in G.edges(data=True)):
        G = _add_travel_times(G)
    return G


# ---------------------------------------------------------------------- #
# Nokta eşleme ve maliyet matrisleri
# ---------------------------------------------------------------------- #
def _node_arrays(G: nx.MultiDiGraph):
    cache = G.graph.get("_node_arrays")
    if cache is None:
        ids = np.array(list(G.nodes))
        lat = np.array([G.nodes[n]["y"] for n in ids], dtype=float)
        lon = np.array([G.nodes[n]["x"] for n in ids], dtype=float)
        cache = (ids, lat, lon)
        G.graph["_node_arrays"] = cache
    return cache


def snap_to_nodes(G: nx.MultiDiGraph, coords: Sequence[LatLon]) -> Tuple[List[int], np.ndarray]:
    """
    Her (enlem, boylam) noktası için en yakın yol düğümünü bulur.
    Returns: (düğüm id listesi, noktanın düğüme uzaklığı [metre])
    """
    from aco.utils import EARTH_RADIUS_KM

    ids, lat, lon = _node_arrays(G)
    lat_r, lon_r = np.radians(lat), np.radians(lon)
    nodes, dists = [], []
    for p_lat, p_lon in coords:
        pl, pg = np.radians(p_lat), np.radians(p_lon)
        a = (np.sin((lat_r - pl) / 2) ** 2
             + np.cos(pl) * np.cos(lat_r) * np.sin((lon_r - pg) / 2) ** 2)
        d = 2 * EARTH_RADIUS_KM * 1000 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        k = int(np.argmin(d))
        nodes.append(ids[k].item())
        dists.append(float(d[k]))
    return nodes, np.array(dists)


def compute_cost_matrices(G: nx.MultiDiGraph, nodes: Sequence[int]) -> Tuple[np.ndarray, np.ndarray]:
    """
    Her düğümden diğerlerine yönlü en kısa yol maliyetleri.
    Her kaynak için tek bir Dijkstra çalıştırılır (n² yerine n çağrı).
    Returns: (mesafe matrisi [km], süre matrisi [dakika]); ulaşılamayan çiftler inf.
    """
    n = len(nodes)
    dist_km = np.full((n, n), np.inf)
    time_min = np.full((n, n), np.inf)
    for i, src in enumerate(nodes):
        lengths = nx.single_source_dijkstra_path_length(G, src, weight="length")
        times = nx.single_source_dijkstra_path_length(G, src, weight="travel_time")
        for j, dst in enumerate(nodes):
            if dst in lengths:
                dist_km[i, j] = lengths[dst] / 1000.0
            if dst in times:
                time_min[i, j] = times[dst] / 60.0
    np.fill_diagonal(dist_km, 0.0)
    np.fill_diagonal(time_min, 0.0)
    return dist_km, time_min


def compute_distance_matrix(G: nx.MultiDiGraph, coords: Sequence[LatLon]) -> np.ndarray:
    """Geriye dönük uyumluluk: koordinatlar için yol mesafesi matrisi (km)."""
    nodes, _ = snap_to_nodes(G, coords)
    return compute_cost_matrices(G, nodes)[0]


# ---------------------------------------------------------------------- #
# Rota geometrisi
# ---------------------------------------------------------------------- #
def _best_edge(G: nx.MultiDiGraph, u: int, v: int, weight: str) -> Dict:
    return min(G[u][v].values(), key=lambda d: d.get(weight, float("inf")))


def route_legs(
    G: nx.MultiDiGraph,
    nodes: Sequence[int],
    route: Sequence[int],
    weight: str = "length",
) -> List[Dict]:
    """
    Rotanın her ayağı (route[k] -> route[k+1]) için yol geometrisi ve maliyetler.
    Returns: [{"from": i, "to": j, "coords": [(lat, lon), ...],
               "length_km": float, "time_min": float}, ...]
    """
    legs = []
    for a, b in zip(route[:-1], route[1:]):
        u, v = nodes[a], nodes[b]
        leg = {"from": a, "to": b, "coords": [], "length_km": 0.0, "time_min": 0.0}
        try:
            path = nx.shortest_path(G, u, v, weight=weight)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            leg.update(length_km=float("inf"), time_min=float("inf"))
            legs.append(leg)
            continue
        coords: List[LatLon] = [(G.nodes[path[0]]["y"], G.nodes[path[0]]["x"])]
        for x, y in zip(path[:-1], path[1:]):
            data = _best_edge(G, x, y, weight)
            leg["length_km"] += data.get("length", 0.0) / 1000.0
            leg["time_min"] += data.get("travel_time", 0.0) / 60.0
            geom = data.get("geometry")
            if geom is not None:
                pts = [(lat, lon) for lon, lat in geom.coords]
                # Geometri yönü kenar yönüyle ters olabilir
                start = (G.nodes[x]["y"], G.nodes[x]["x"])
                if _sq(pts[-1], start) < _sq(pts[0], start):
                    pts.reverse()
                coords.extend(pts[1:])
            else:
                coords.append((G.nodes[y]["y"], G.nodes[y]["x"]))
        leg["coords"] = coords
        legs.append(leg)
    return legs


def _sq(p: LatLon, q: LatLon) -> float:
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
