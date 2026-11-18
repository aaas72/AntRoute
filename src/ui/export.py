# -*- coding: utf-8 -*-
"""
src/ui/export.py

Sonuçların dışa aktarımı: rota tablosu, Google Maps yol tarifi bağlantıları
ve süre biçimlendirme. Streamlit'e bağımlı değildir (test edilebilir).
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple
from urllib.parse import urlencode

import pandas as pd

LatLon = Tuple[float, float]

# Google Maps URL'si başlangıç + varış dışında en fazla 9 ara nokta destekler
GMAPS_MAX_STOPS = 11


def format_minutes(minutes: float) -> str:
    if minutes != minutes or minutes == float("inf"):  # NaN / inf
        return "—"
    total = int(round(minutes))
    h, m = divmod(total, 60)
    return f"{h} sa {m:02d} dk" if h else f"{m} dk"


def route_table(names: Sequence[str], coords: Sequence[LatLon], route: Sequence[int],
                legs: List[Dict]) -> pd.DataFrame:
    """Rotanın ayak ayak (durak -> durak) tablosu."""
    rows, cum_km, cum_min = [], 0.0, 0.0
    for k, leg in enumerate(legs, start=1):
        cum_km += leg["length_km"]
        cum_min += leg["time_min"]
        a, b = leg["from"], leg["to"]
        rows.append({
            "Ayak": k,
            "Nereden": names[a],
            "Nereye": names[b],
            "Mesafe (km)": round(leg["length_km"], 3),
            "Süre (dk)": round(leg["time_min"], 1),
            "Toplam (km)": round(cum_km, 3),
            "Toplam süre (dk)": round(cum_min, 1),
            "Varış enlem": coords[b][0],
            "Varış boylam": coords[b][1],
        })
    return pd.DataFrame(rows)


def _gmaps_url(points: Sequence[LatLon]) -> str:
    fmt = lambda p: f"{p[0]:.6f},{p[1]:.6f}"  # noqa: E731
    params = {
        "api": 1,
        "origin": fmt(points[0]),
        "destination": fmt(points[-1]),
        "travelmode": "driving",
    }
    if len(points) > 2:
        params["waypoints"] = "|".join(fmt(p) for p in points[1:-1])
    return "https://www.google.com/maps/dir/?" + urlencode(params, safe=",|")


def google_maps_links(coords: Sequence[LatLon], route: Sequence[int]) -> List[str]:
    """
    Rotayı Google Maps yol tarifi bağlantılarına çevirir. Durak sayısı Google'ın
    sınırını aşarsa rota, uç noktaları ortak olan parçalara bölünür.
    """
    points = [coords[i] for i in route]
    if len(points) < 2:
        return []
    links, step = [], GMAPS_MAX_STOPS - 1
    for s in range(0, len(points) - 1, step):
        links.append(_gmaps_url(points[s:s + GMAPS_MAX_STOPS]))
    return links
