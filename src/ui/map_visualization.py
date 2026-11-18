# -*- coding: utf-8 -*-
"""
src/ui/map_visualization.py

Folium haritaları:
  - build_route_map  : optimize edilmiş rotayı gerçek yol geometrisiyle çizer
  - build_picker_map : nokta seçimi için mevcut durakları gösteren harita
"""

from __future__ import annotations

from html import escape
from typing import Dict, List, Optional, Sequence, Tuple

import folium
from folium.plugins import AntPath, Fullscreen

LatLon = Tuple[float, float]

DEPOT_COLOR = "#1b7f3b"
STOP_COLOR = "#1f5fbf"
ROUTE_COLOR = "#d63a2f"


def _number_icon(label: str, color: str, size: int = 26) -> folium.DivIcon:
    html = (
        f'<div style="background:{color};color:#fff;border:2px solid #fff;'
        f"border-radius:50%;width:{size}px;height:{size}px;line-height:{size - 4}px;"
        f"text-align:center;font:600 12px/{size - 4}px system-ui,sans-serif;"
        f'box-shadow:0 1px 4px rgba(0,0,0,.45)">{escape(label)}</div>'
    )
    return folium.DivIcon(html=html, icon_size=(size, size), icon_anchor=(size // 2, size // 2))


def _base_map(coords: Sequence[LatLon], center: Optional[LatLon] = None) -> folium.Map:
    if center is None:
        center = (
            sum(c[0] for c in coords) / len(coords),
            sum(c[1] for c in coords) / len(coords),
        )
    m = folium.Map(location=center, zoom_start=13, tiles="OpenStreetMap", control_scale=True)
    Fullscreen(position="topleft").add_to(m)
    return m


def build_route_map(
    names: Sequence[str],
    coords: Sequence[LatLon],
    route: Sequence[int],
    legs: Optional[List[Dict]] = None,
    animate: bool = True,
) -> folium.Map:
    """
    Args:
      - names, coords: durak adları ve (enlem, boylam) koordinatları
      - route: [0, 3, 1, 2, 0] gibi indeks listesi (ilk eleman depo)
      - legs: osm_data.route_legs() çıktısı; verilirse gerçek yol geometrisi çizilir,
              verilmezse duraklar düz çizgiyle birleştirilir.
      - animate: True ise rota hareketli (AntPath) çizgiyle gösterilir.
    """
    m = _base_map(coords)
    closed = len(route) > 1 and route[0] == route[-1]
    order = list(route[:-1]) if closed else list(route)

    if legs:
        for k, leg in enumerate(legs):
            if not leg["coords"]:
                continue
            tooltip = (
                f"{k + 1}. ayak: {names[leg['from']]} → {names[leg['to']]}"
                f" · {leg['length_km']:.2f} km · {leg['time_min']:.1f} dk"
            )
            line_cls = AntPath if animate else folium.PolyLine
            kwargs = {"delay": 1200, "dash_array": [12, 24], "pulse_color": "#ffffff"} if animate else {}
            line_cls(
                locations=leg["coords"], color=ROUTE_COLOR, weight=5, opacity=0.85,
                tooltip=tooltip, **kwargs,
            ).add_to(m)
    else:
        path = [coords[i] for i in route]
        (AntPath if animate else folium.PolyLine)(
            locations=path, color=ROUTE_COLOR, weight=4, opacity=0.8,
            tooltip="Kuş uçuşu bağlantılar (yol ağı yok)",
        ).add_to(m)

    for pos, idx in enumerate(order):
        is_depot = pos == 0
        label = "D" if is_depot else str(pos)
        popup = (
            f"<b>{escape(names[idx])}</b><br>"
            f"{'Başlangıç (depo)' if is_depot else f'Sıra: {pos}'}<br>"
            f"{coords[idx][0]:.5f}, {coords[idx][1]:.5f}"
        )
        folium.Marker(
            location=coords[idx],
            popup=folium.Popup(popup, max_width=250),
            tooltip=f"{label} · {names[idx]}",
            icon=_number_icon(label, DEPOT_COLOR if is_depot else STOP_COLOR, 30 if is_depot else 26),
            z_index_offset=1000 if is_depot else 0,
        ).add_to(m)

    all_pts = [p for leg in (legs or []) for p in leg["coords"]] or list(coords)
    lats = [p[0] for p in all_pts]
    lons = [p[1] for p in all_pts]
    m.fit_bounds([(min(lats), min(lons)), (max(lats), max(lons))], padding=(30, 30))
    return m


def build_picker_map(
    names: Sequence[str],
    coords: Sequence[LatLon],
    center: LatLon,
) -> folium.Map:
    """Mevcut durakları numaralı işaretlerle gösteren, tıklanabilir seçim haritası."""
    # Not: Harita gizli bir sekmede (genişlik 0) oluşturulabildiği için fit_bounds
    # yanlış yakınlaştırma üretir; merkez ve zoom burada hesaplanır.
    zoom = 13
    if len(coords) >= 2:
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        center = ((min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2)
        zoom = _zoom_for_extent(max(lats) - min(lats), max(lons) - min(lons), center[0])
    m = _base_map(coords or [center], center=center)
    m.options["zoom"] = zoom
    for i, (name, c) in enumerate(zip(names, coords)):
        folium.Marker(
            location=c,
            tooltip=f"{i + 1} · {name}",
            icon=_number_icon(str(i + 1), DEPOT_COLOR if i == 0 else STOP_COLOR),
        ).add_to(m)
    return m


def _zoom_for_extent(lat_span: float, lon_span: float, mid_lat: float = 0.0,
                     width_px: int = 650, height_px: int = 400) -> int:
    """Verilen enlem/boylam aralığını yaklaşık width_px x height_px alana sığdıran Leaflet zoom'u."""
    import math

    lon_span = max(lon_span, 1e-4) * 1.2  # kenar payı
    lat_span = max(lat_span, 1e-4) * 1.2
    z_lon = math.log2(360 * width_px / (256 * lon_span))
    # Web Mercator: 1° enlem, 1° boylamdan 1/cos(enlem) kat daha uzun görünür
    z_lat = math.log2(360 * math.cos(math.radians(mid_lat)) * height_px / (256 * lat_span))
    return int(max(3, min(17, math.floor(min(z_lon, z_lat)))))
