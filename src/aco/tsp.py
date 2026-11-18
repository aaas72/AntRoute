# -*- coding: utf-8 -*-
"""
src/aco/tsp.py

TSP için yardımcı/karşılaştırma algoritmaları:
  - route_length      : bir rotanın toplam maliyeti
  - nearest_neighbor  : En Yakın Komşu sezgiseli (hızlı, temel çözüm)
  - two_opt           : 2-opt yerel arama (simetrik ve asimetrik matrisler için)
  - brute_force       : küçük problemler için kesin (optimal) çözüm

Rota gösterimi:
  - Kapalı tur (return_to_start=True): [s, a, b, ..., s]  (başlangıca dönüş dahil)
  - Açık yol  (return_to_start=False): [s, a, b, ..., z]
"""

from __future__ import annotations

import itertools
from typing import List, Optional, Sequence

import numpy as np

BRUTE_FORCE_LIMIT = 9  # (n-1)! permütasyon; 9 nokta = 40 320 permütasyon


def route_length(dist: np.ndarray, route: Sequence[int]) -> float:
    """Rotadaki ardışık düğümler arasındaki maliyetlerin toplamı."""
    if len(route) < 2:
        return 0.0
    r = np.asarray(route, dtype=int)
    return float(dist[r[:-1], r[1:]].sum())


def _close(seq: List[int], closed: bool) -> List[int]:
    return seq + [seq[0]] if closed and seq else list(seq)


def nearest_neighbor(dist: np.ndarray, start: int = 0, return_to_start: bool = True) -> List[int]:
    """Her adımda en yakın ziyaret edilmemiş noktaya giden açgözlü rota."""
    n = dist.shape[0]
    visited = np.zeros(n, dtype=bool)
    seq = [start]
    visited[start] = True
    for _ in range(n - 1):
        row = np.where(visited, np.inf, dist[seq[-1]])
        nxt = int(np.argmin(row))
        seq.append(nxt)
        visited[nxt] = True
    return _close(seq, return_to_start)


def two_opt(
    dist: np.ndarray,
    route: Sequence[int],
    return_to_start: bool = True,
    fix_start: bool = True,
    max_passes: int = 50,
) -> List[int]:
    """
    2-opt yerel arama: bir rota parçasını ters çevirerek maliyeti düşürmeye çalışır.

    Asimetrik matrislerde (tek yönlü yollar) ters çevrilen parçanın iç kenarlarının
    maliyeti de değiştiği için, fark (delta) bu kenarlar dahil hesaplanır.
    """
    closed = return_to_start
    seq = list(route[:-1]) if closed and len(route) > 1 and route[0] == route[-1] else list(route)
    n = len(seq)
    if n < 3:
        return _close(seq, closed)

    symmetric = bool(np.allclose(dist, dist.T))
    i_min = 1 if (closed or fix_start) else 0

    def d(a: Optional[int], b: Optional[int]) -> float:
        if a is None or b is None:
            return 0.0
        return float(dist[a, b])

    for _ in range(max_passes):
        improved = False
        for i in range(i_min, n - 1):
            for j in range(i + 1, n):
                prev = seq[i - 1] if i > 0 else None
                if j + 1 < n:
                    nxt = seq[j + 1]
                else:
                    nxt = seq[0] if closed else None
                old = d(prev, seq[i]) + d(seq[j], nxt)
                new = d(prev, seq[j]) + d(seq[i], nxt)
                if not symmetric:
                    seg = np.asarray(seq[i:j + 1])
                    old += float(dist[seg[:-1], seg[1:]].sum())
                    new += float(dist[seg[1:], seg[:-1]].sum())
                if new < old - 1e-12:
                    seq[i:j + 1] = reversed(seq[i:j + 1])
                    improved = True
        if not improved:
            break
    return _close(seq, closed)


def brute_force(dist: np.ndarray, start: int = 0, return_to_start: bool = True) -> List[int]:
    """Başlangıç noktası sabitken tüm permütasyonları dener (yalnızca küçük n için)."""
    n = dist.shape[0]
    if n > BRUTE_FORCE_LIMIT:
        raise ValueError(f"brute_force en fazla {BRUTE_FORCE_LIMIT} nokta destekler (n={n}).")
    others = [i for i in range(n) if i != start]
    best_seq, best_len = None, float("inf")
    for perm in itertools.permutations(others):
        seq = [start, *perm]
        length = route_length(dist, _close(seq, return_to_start))
        if length < best_len:
            best_len, best_seq = length, seq
    return _close(best_seq or [start], return_to_start)
