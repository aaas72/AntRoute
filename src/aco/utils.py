# -*- coding: utf-8 -*-
"""
src/aco/utils.py

ACO algoritması veya başka yerler için yardımcı fonksiyonlar içerir.
Örnek: Haversine mesafesi ve yol ağı yokken kullanılan yaklaşık mesafe matrisi.
"""

import math
from typing import Sequence, Tuple

import numpy as np

EARTH_RADIUS_KM = 6371.0

def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """
    İki nokta arasındaki büyük daire (great-circle) mesafesini
    Haversine formülü ile hesaplar.
    Args:
      - coord1: (latitude, longitude) formatında birinci nokta.
      - coord2: (latitude, longitude) formatında ikinci nokta.
    Returns:
      - Mesafe (kilometre cinsinden).
    """
    R = EARTH_RADIUS_KM

    lat1, lon1 = coord1
    lat2, lon2 = coord2

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def haversine_matrix(
    coords: Sequence[Tuple[float, float]],
    detour_factor: float = 1.3,
) -> np.ndarray:
    """
    Kuş uçuşu (Haversine) mesafe matrisi (km).

    Yol ağı verisi yokken yaklaşık sonuç vermek için kullanılır. Şehir içi yollar
    düz çizgiden daha uzun olduğundan sonuç `detour_factor` ile çarpılır
    (şehir içi için tipik değer ~1.3).
    """
    pts = np.radians(np.asarray(coords, dtype=float))
    if pts.size == 0:
        return np.zeros((0, 0))
    lat = pts[:, 0][:, None]
    lon = pts[:, 1][:, None]
    d_lat = lat.T - lat
    d_lon = lon.T - lon
    a = np.sin(d_lat / 2) ** 2 + np.cos(lat) * np.cos(lat.T) * np.sin(d_lon / 2) ** 2
    dist = 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return dist * detour_factor
