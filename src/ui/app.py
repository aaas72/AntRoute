# -*- coding: utf-8 -*-
"""
src/ui/app.py

Streamlit arayüzü:
- Durakları hazır listeden, haritaya tıklayarak veya CSV'den eklemek ve tabloda düzenlemek
- Depo (başlangıç), dönüş ve optimizasyon kriterini (mesafe / süre) seçmek
- ACO parametrelerini ayarlamak
- Sonuçları gerçek yol geometrili harita, yakınsama grafiği, algoritma
  karşılaştırması ve dışa aktarım (CSV, Google Maps) ile göstermek

Çalıştırma:  streamlit run src/ui/app.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# src/ klasörünü PYTHONPATH'e ekle (streamlit run hangi klasörden çalıştırılırsa çalıştırılsın)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aco.algorithm import ACO  # noqa: E402
from aco.tsp import BRUTE_FORCE_LIMIT, brute_force, nearest_neighbor, route_length, two_opt  # noqa: E402
from aco.utils import haversine_matrix  # noqa: E402
from data.location_data import load_default_locations, load_locations_from_csv  # noqa: E402
from data.osm_data import (  # noqa: E402
    DEFAULT_CENTER, FALLBACK_SPEED_KPH, GRAPHML_PATH,
    compute_cost_matrices, download_network, load_network, route_legs, snap_to_nodes,
)
from ui.export import format_minutes, google_maps_links, route_table  # noqa: E402
from ui.map_visualization import build_picker_map, build_route_map  # noqa: E402
from ui.plots import comparison_figure, convergence_figure, distance_heatmap_figure  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COLS = ["Ad", "Enlem", "Boylam"]
SNAP_WARN_M = 300  # noktanın yola uzaklığı bu değeri aşarsa uyar
OBJECTIVES = {"distance": "Mesafe (km)", "time": "Süre (dk)"}


# ====================================================================== #
# Önbellekli veri erişimi
# ====================================================================== #
@st.cache_resource(show_spinner="Yol ağı yükleniyor...")
def get_network(mtime: float):
    """GraphML dosyası değiştiğinde (mtime) yeniden yüklenir."""
    return load_network(GRAPHML_PATH)


def network_available() -> bool:
    return GRAPHML_PATH.exists()


@st.cache_data(show_spinner=False, max_entries=32)
def get_road_matrices(_G, mtime: float, coords: Tuple[Tuple[float, float], ...]):
    nodes, snap_m = snap_to_nodes(_G, coords)
    dist_km, time_min = compute_cost_matrices(_G, nodes)
    return nodes, snap_m, dist_km, time_min


# ====================================================================== #
# Durak listesi yönetimi
# ====================================================================== #
def init_state() -> None:
    ss = st.session_state
    ss.setdefault("stops", pd.DataFrame(columns=COLS).astype({"Enlem": float, "Boylam": float}))
    ss.setdefault("stops_version", 0)
    ss.setdefault("last_click", None)
    ss.setdefault("results", None)


def set_stops(df: pd.DataFrame) -> None:
    """Durak listesini programatik olarak değiştirir ve tablo editörünü sıfırlar."""
    st.session_state.stops = df[COLS].reset_index(drop=True)
    st.session_state.stops_version += 1
    st.rerun()


def add_stops(current: pd.DataFrame, new: pd.DataFrame) -> None:
    combined = pd.concat([current[COLS], new[COLS]], ignore_index=True)
    key = combined[["Enlem", "Boylam"]].round(6).astype(str).agg(",".join, axis=1)
    set_stops(combined[~key.duplicated()])


def clean_stops(df: pd.DataFrame) -> pd.DataFrame:
    """Tablodaki eksik/geçersiz satırları ayıklar ve isimleri benzersiz yapar."""
    df = df.copy()
    df["Enlem"] = pd.to_numeric(df["Enlem"], errors="coerce")
    df["Boylam"] = pd.to_numeric(df["Boylam"], errors="coerce")
    df = df.dropna(subset=["Enlem", "Boylam"])
    df = df[df["Enlem"].between(-90, 90) & df["Boylam"].between(-180, 180)]
    names, seen = [], {}
    for i, n in enumerate(df["Ad"].tolist()):
        n = str(n).strip() if isinstance(n, str) and n.strip() else f"Durak {i + 1}"
        if n in seen:
            seen[n] += 1
            n = f"{n} ({seen[n]})"
        else:
            seen[n] = 1
        names.append(n)
    df["Ad"] = names
    return df.reset_index(drop=True)


def stops_editor() -> pd.DataFrame:
    ss = st.session_state
    st.markdown("**Durak listesi** · ilk satır varsayılan depo; hücreleri düzenleyebilir, satır silebilirsiniz.")
    edited = st.data_editor(
        ss.stops,
        key=f"stops_editor_{ss.stops_version}",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        height=min(420, 38 + 35 * (len(ss.stops) + 1)),
        column_config={
            "Ad": st.column_config.TextColumn("Ad", width="medium"),
            "Enlem": st.column_config.NumberColumn("Enlem", min_value=-90, max_value=90, format="%.5f",
                                                   width="small"),
            "Boylam": st.column_config.NumberColumn("Boylam", min_value=-180, max_value=180, format="%.5f",
                                                    width="small"),
        },
    )
    c1, c2 = st.columns(2)
    if c1.button(":material/delete_sweep: Tümünü temizle", width="stretch", disabled=edited.empty):
        st.session_state.results = None
        set_stops(edited.iloc[0:0])
    csv = clean_stops(edited).rename(columns={"Ad": "name", "Enlem": "latitude", "Boylam": "longitude"})
    c2.download_button(
        ":material/download: Listeyi CSV indir", csv.to_csv(index=False).encode("utf-8"),
        "duraklar.csv", "text/csv", width="stretch", disabled=edited.empty,
    )
    return edited


def stop_inputs(current: pd.DataFrame) -> None:
    tab_list, tab_map, tab_csv = st.tabs([
        ":material/list: Hazır noktalar", ":material/add_location_alt: Haritadan ekle",
        ":material/upload_file: CSV yükle",
    ])

    with tab_list:
        defaults = load_default_locations()
        existing = set(current["Ad"].astype(str))
        options = [n for n in defaults if n not in existing]
        chosen = st.multiselect(
            "Elâzığ'daki hazır noktalar (yazarak arayabilirsiniz)", options,
            placeholder="Nokta seçin...",
        )
        c1, c2 = st.columns(2)
        if c1.button(":material/add: Seçilenleri ekle", disabled=not chosen, width="stretch", type="primary"):
            add_stops(current, pd.DataFrame(
                [(n, *defaults[n]) for n in chosen], columns=COLS))
        if c2.button(f":material/playlist_add: Tümünü ekle ({len(options)})", disabled=not options,
                     width="stretch"):
            add_stops(current, pd.DataFrame(
                [(n, *defaults[n]) for n in options], columns=COLS))

    with tab_map:
        st.caption("Haritaya her tıklama yeni bir durak ekler. Numaralar listedeki sırayı gösterir.")
        valid = clean_stops(current)
        m = build_picker_map(
            valid["Ad"].tolist(), list(zip(valid["Enlem"], valid["Boylam"])), DEFAULT_CENTER)
        out = st_folium(m, key="picker_map", height=430, use_container_width=True,
                        returned_objects=["last_clicked"])
        click = (out or {}).get("last_clicked")
        if click:
            pt = (round(click["lat"], 6), round(click["lng"], 6))
            if pt != st.session_state.last_click:
                st.session_state.last_click = pt
                k = len(current) + 1
                add_stops(current, pd.DataFrame([(f"Nokta {k}", *pt)], columns=COLS))

    with tab_csv:
        st.caption("Kolonlar: `name, latitude, longitude` (alternatif: `ad, enlem, boylam`). "
                   "Ayraç `,` veya `;` olabilir.")
        sample = pd.DataFrame(
            [(n, *c) for n, c in list(load_default_locations().items())[:5]],
            columns=["name", "latitude", "longitude"])
        st.download_button(":material/description: Örnek CSV şablonu",
                           sample.to_csv(index=False).encode("utf-8"), "ornek_duraklar.csv",
                           "text/csv")
        uploaded = st.file_uploader("CSV dosyası seçin", type=["csv", "txt"])
        if uploaded is not None:
            try:
                locs = load_locations_from_csv(uploaded)
            except Exception as e:  # kullanıcı dosyası: hatayı göster
                st.error(f"CSV okunamadı: {e}")
            else:
                st.success(f"{len(locs)} nokta okundu.")
                df_new = pd.DataFrame([(n, *c) for n, c in locs.items()], columns=COLS)
                c1, c2 = st.columns(2)
                if c1.button(":material/add: Listeye ekle", type="primary", width="stretch"):
                    add_stops(current, df_new)
                if c2.button(":material/swap_horiz: Listeyi değiştir", width="stretch"):
                    set_stops(df_new)


# ====================================================================== #
# Kenar çubuğu: ayarlar
# ====================================================================== #
def sidebar_settings(has_network: bool) -> Dict:
    with st.sidebar:
        st.header("Ayarlar")
        st.subheader("Mesafe kaynağı")
        if has_network:
            use_network = st.toggle("Gerçek yol ağı (OSM)", value=True,
                                    help="Kapalıysa kuş uçuşu mesafe × 1.3 kullanılır.")
        else:
            use_network = False
            st.warning("Yol ağı dosyası yok; kuş uçuşu yaklaşık mesafe kullanılacak.")
            if st.button(":material/cloud_download: Elâzığ yol ağını indir", width="stretch"):
                with st.spinner("OpenStreetMap'ten indiriliyor (1-3 dk)..."):
                    try:
                        download_network()
                    except Exception as e:
                        st.error(f"İndirme başarısız: {e}")
                    else:
                        st.rerun()

        objective = st.radio(
            "Optimizasyon kriteri", list(OBJECTIVES), format_func=OBJECTIVES.get, horizontal=True,
            help="Süre, OSM'deki hız sınırlarına (yoksa yol tipine göre varsayılan hızlara) dayanır.",
        )

        st.subheader("ACO parametreleri")
        ant_count = st.number_input("Karınca sayısı", 2, 200, 20, 1)
        iterations = st.number_input("Maksimum iterasyon", 10, 2000, 100, 10)
        seed = st.number_input("Rastgele tohum", 0, 999_999, 42, 1)
        use_patience = st.checkbox("Erken durdurma", value=True,
                                   help="En iyi rota belirli sayıda iterasyon iyileşmezse dur.")
        patience = st.number_input("Sabır (iterasyon)", 5, 1000, 30, 5,
                                   disabled=not use_patience)

        with st.expander("Gelişmiş ayarlar"):
            alpha = st.slider("α – feromon etkisi", 0.1, 5.0, 1.0, 0.1)
            beta = st.slider("β – mesafe etkisi", 0.1, 8.0, 3.0, 0.1)
            rho = st.slider("ρ – buharlaşma oranı", 0.01, 1.0, 0.3, 0.01)
            Q = st.number_input("Q – feromon sabiti", 1, 1000, 100, 1)
            elitist = st.slider("Elitist ağırlık", 0.0, 10.0, 1.0, 0.5,
                                help="En iyi rotaya eklenen ekstra feromon (0 = kapalı).")
            local_search = st.checkbox("2-opt yerel arama", value=True,
                                       help="Her iterasyonun en iyi rotasındaki kesişmeleri giderir.")
            animate = st.checkbox("Haritada hareketli rota", value=True)

    return {
        "use_network": use_network, "objective": objective, "ant_count": int(ant_count),
        "iterations": int(iterations), "seed": int(seed),
        "patience": int(patience) if use_patience else None,
        "alpha": alpha, "beta": beta, "rho": rho, "Q": float(Q), "elitist": elitist,
        "local_search": local_search, "animate": animate,
    }


# ====================================================================== #
# Optimizasyon
# ====================================================================== #
def run_optimization(stops: pd.DataFrame, depot: int, closed: bool, cfg: Dict) -> Dict:
    names = stops["Ad"].tolist()
    coords = [(float(a), float(b)) for a, b in zip(stops["Enlem"], stops["Boylam"])]
    n = len(coords)
    G = nodes = None
    snap_m = np.zeros(n)

    t0 = time.perf_counter()
    if cfg["use_network"]:
        mtime = GRAPHML_PATH.stat().st_mtime
        G = get_network(mtime)
        with st.spinner(f"{n} durak için yol mesafeleri hesaplanıyor..."):
            nodes, snap_m, dist_km, time_min = get_road_matrices(G, mtime, tuple(coords))
    else:
        dist_km = haversine_matrix(coords)
        time_min = dist_km / FALLBACK_SPEED_KPH * 60.0
    matrix_s = time.perf_counter() - t0

    cost = dist_km if cfg["objective"] == "distance" else time_min
    bar = st.progress(0.0, text="ACO çalışıyor...")
    step = max(1, cfg["iterations"] // 50)

    def on_progress(it: int, total: int, best: float) -> None:
        if it % step == 0 or it == total:
            bar.progress(it / total, text=f"İterasyon {it}/{total} · en iyi: {best:.2f}")

    aco = ACO(
        cost, ant_count=cfg["ant_count"], alpha=cfg["alpha"], beta=cfg["beta"], rho=cfg["rho"],
        Q=cfg["Q"], seed=cfg["seed"], start=depot, return_to_start=closed,
        elitist_weight=cfg["elitist"], local_search=cfg["local_search"],
    )
    route, best_cost, history = aco.run(cfg["iterations"], cfg["patience"], on_progress)
    bar.empty()

    # Karşılaştırma için temel yöntemler (aynı maliyet matrisi üzerinde)
    safe = aco.distances  # inf yerine ceza değerli matris
    t = time.perf_counter()
    nn = nearest_neighbor(safe, depot, closed)
    nn_s = time.perf_counter() - t
    t = time.perf_counter()
    nn2 = two_opt(safe, nn, closed)
    nn2_s = time.perf_counter() - t
    comparison = [
        {"Yöntem": "En Yakın Komşu", "Maliyet": route_length(safe, nn), "Süre (sn)": nn_s},
        {"Yöntem": "En Yakın Komşu + 2-opt", "Maliyet": route_length(safe, nn2), "Süre (sn)": nn2_s},
        {"Yöntem": "ACO (bu çalıştırma)", "Maliyet": best_cost, "Süre (sn)": aco.runtime_s},
    ]
    optimum = None
    if n <= BRUTE_FORCE_LIMIT:
        t = time.perf_counter()
        opt_route = brute_force(safe, depot, closed)
        optimum = route_length(safe, opt_route)
        comparison.append({"Yöntem": "Kesin optimum (kaba kuvvet)", "Maliyet": optimum,
                           "Süre (sn)": time.perf_counter() - t})

    # Rota ayakları: gerçek yol geometrisi veya düz çizgi
    if G is not None:
        weight = "length" if cfg["objective"] == "distance" else "travel_time"
        legs = route_legs(G, nodes, route, weight=weight)
    else:
        legs = [{"from": a, "to": b, "coords": [coords[a], coords[b]],
                 "length_km": float(dist_km[a, b]), "time_min": float(time_min[a, b])}
                for a, b in zip(route[:-1], route[1:])]

    return {
        "names": names, "coords": coords, "route": route, "legs": legs,
        "best_cost": best_cost, "history": history, "comparison": comparison,
        "optimum": optimum, "dist_km": dist_km, "time_min": time_min,
        "snap_m": snap_m, "feasible": aco.is_feasible(route), "cfg": dict(cfg),
        "closed": closed, "iterations_run": aco.iterations_run, "aco_s": aco.runtime_s,
        "matrix_s": matrix_s, "signature": stops_signature(stops, depot, closed),
    }


def stops_signature(stops: pd.DataFrame, depot: int, closed: bool) -> Tuple:
    return (tuple(map(tuple, stops[COLS].astype(str).values)), depot, closed)


# ====================================================================== #
# Sonuçlar
# ====================================================================== #
def show_results(res: Dict, current_signature: Optional[Tuple]) -> None:
    names, coords, route, legs = res["names"], res["coords"], res["route"], res["legs"]
    cfg = res["cfg"]
    unit = "km" if cfg["objective"] == "distance" else "dk"
    total_km = sum(l["length_km"] for l in legs)
    total_min = sum(l["time_min"] for l in legs)

    st.divider()
    st.header("Sonuçlar")
    if current_signature != res["signature"]:
        st.info("Duraklar veya rota ayarları değişti; aşağıdaki sonuçlar önceki çalıştırmaya ait.",
                icon=":material/history:")
    if not res["feasible"]:
        st.error("Bazı duraklar arasında yol bulunamadı (tek yönlü / kopuk yol). Rota ulaşılamayan "
                 "bir ayak içeriyor; ilgili durakların konumunu kontrol edin.")
    far = [(names[i], d) for i, d in enumerate(res["snap_m"]) if d > SNAP_WARN_M]
    if far:
        st.warning("Yola uzak duraklar (en yakın yol düğümüne mesafe): " +
                   ", ".join(f"{n} ({d:.0f} m)" for n, d in far))
    if not cfg["use_network"]:
        st.caption("Not: Mesafeler kuş uçuşu × 1.3, süreler 30 km/sa ortalama hız ile tahmin edildi.")

    nn_cost = res["comparison"][0]["Maliyet"]
    gain = (nn_cost - res["best_cost"]) / nn_cost * 100 if nn_cost > 0 else 0.0
    c = st.columns(4)
    c[0].metric("Toplam mesafe", f"{total_km:.2f} km")
    c[1].metric("Tahmini sürüş süresi", format_minutes(total_min))
    c[2].metric("En Yakın Komşu'ya göre", f"%{gain:.1f} daha iyi" if gain > 0.05 else "eşit",
                help="Aynı kriterle En Yakın Komşu sezgiseline göre iyileşme.")
    if res["optimum"] is not None:
        gap = (res["best_cost"] - res["optimum"]) / res["optimum"] * 100 if res["optimum"] else 0
        c[3].metric("Optimuma uzaklık", "optimum ✓" if gap < 1e-6 else f"%{gap:.2f}")
    else:
        c[3].metric("Hesaplama süresi", f"{res['aco_s'] + res['matrix_s']:.1f} sn",
                    help=f"Matris: {res['matrix_s']:.1f} sn · ACO: {res['aco_s']:.1f} sn")

    tabs = st.tabs([":material/map: Harita", ":material/format_list_numbered: Rota detayı",
                    ":material/show_chart: Yakınsama", ":material/balance: Karşılaştırma",
                    ":material/grid_on: Maliyet matrisi"])

    with tabs[0]:
        m = build_route_map(names, coords, route, legs, animate=cfg["animate"])
        st_folium(m, key="result_map", height=580, use_container_width=True, returned_objects=[])

    with tabs[1]:
        table = route_table(names, coords, route, legs)
        st.dataframe(table, hide_index=True, width="stretch")
        st.markdown("**Rota:** " + " → ".join(names[i] for i in route))
        links = google_maps_links(coords, route)
        cols = st.columns(1 + max(len(links), 2))
        cols[0].download_button(":material/download: Rotayı CSV indir",
                                table.to_csv(index=False).encode("utf-8-sig"),
                                "optimize_rota.csv", "text/csv", width="stretch")
        for k, url in enumerate(links, 1):
            label = "Google Maps" + (f" ({k}/{len(links)})" if len(links) > 1 else "'te aç")
            cols[k].link_button(f":material/directions_car: {label}", url, width="stretch")

    with tabs[2]:
        hist = res["history"]
        best_vals = [h["best_distance"] for h in hist]
        first_best = next(h["iteration"] for h in hist if h["best_distance"] == best_vals[-1])
        st.plotly_chart(convergence_figure(hist, unit), width="stretch")
        st.caption(f"{res['iterations_run']} iterasyon çalıştı; en iyi rota ilk kez "
                   f"{first_best}. iterasyonda bulundu.")

    with tabs[3]:
        rows = res["comparison"]
        best = min(r["Maliyet"] for r in rows)
        df = pd.DataFrame([{
            "Yöntem": r["Yöntem"], f"Maliyet ({unit})": round(r["Maliyet"], 3),
            "En iyiye fark (%)": round((r["Maliyet"] - best) / best * 100, 2) if best else 0,
            "Hesaplama (sn)": round(r["Süre (sn)"], 4),
        } for r in rows])
        st.plotly_chart(comparison_figure(rows, unit), width="stretch")
        st.dataframe(df, hide_index=True, width="stretch")
        if res["optimum"] is None:
            st.caption(f"Kesin optimum yalnızca {BRUTE_FORCE_LIMIT} veya daha az durak için hesaplanır.")

    with tabs[4]:
        which = st.radio("Matris", ["Mesafe (km)", "Süre (dk)"], horizontal=True, key="matrix_kind")
        mat = res["dist_km"] if which.startswith("Mesafe") else res["time_min"]
        u = "km" if which.startswith("Mesafe") else "dk"
        st.plotly_chart(distance_heatmap_figure(mat, names, u), width="stretch")
        asym = np.nanmax(np.abs(np.where(np.isfinite(mat), mat - mat.T, 0)))
        if asym > 1e-6:
            st.caption(f"Matris asimetrik (tek yönlü yollar): gidiş-dönüş farkı en fazla {asym:.2f} {u}.")


# ====================================================================== #
# Ana sayfa
# ====================================================================== #
def main() -> None:
    st.set_page_config(page_title="AntRoute · Elâzığ Rota Optimizasyonu", page_icon=":material/route:",
                       layout="wide")
    init_state()
    has_network = network_available()
    cfg = sidebar_settings(has_network)

    st.title(":material/route: AntRoute")
    st.markdown("**Elâzığ Teslimat Rotası Optimizasyonu**")
    st.caption("Karınca Kolonisi Optimizasyonu (ACO) ile gerçek yol ağı üzerinde en kısa teslimat rotası.")

    st.subheader("1. Teslimat durakları")
    col_add, col_list = st.columns([5, 4], gap="large")
    with col_list:
        current = stops_editor()
    with col_add:
        stop_inputs(current)

    stops = clean_stops(current)
    st.subheader("2. Rota")
    if len(stops) < 2:
        st.info("Optimizasyon için en az 2 durak ekleyin.", icon=":material/info:")
        return

    c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="bottom")
    depot = c1.selectbox("Başlangıç noktası (depo)", range(len(stops)),
                         format_func=lambda i: f"{i + 1}. {stops['Ad'][i]}")
    closed = c2.toggle("Depoya geri dön", value=True)
    run = c3.button(":material/rocket_launch: Optimizasyonu başlat", type="primary", width="stretch")

    if run:
        try:
            st.session_state.results = run_optimization(stops, depot, closed, cfg)
        except FileNotFoundError as e:
            st.error(f"Hata: {e}")

    if st.session_state.results is not None:
        show_results(st.session_state.results, stops_signature(stops, depot, closed))


if __name__ == "__main__":
    main()
