# -*- coding: utf-8 -*-
"""
src/aco/algorithm.py

Ant Colony Optimization (ACO) algoritmasını
Travelling Salesman Problem (TSP) benzeri teslimat problemleri için uygular.

Klasik Ant System'e göre eklenenler:
  - Sabit başlangıç noktası (depo) ve açık/kapalı rota desteği
  - Asimetrik mesafe matrisleri (tek yönlü yollar) için yönlü feromon
  - Elitist strateji: şimdiye kadarki en iyi rota ekstra feromon bırakır
  - Her iterasyonun en iyi rotasına 2-opt yerel arama
  - Erken durdurma (patience) ve ilerleme geri çağrısı (progress callback)
  - Ulaşılamayan nokta çiftleri (inf mesafe) için ceza değeri
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from .tsp import nearest_neighbor, route_length, two_opt

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, float], None]


class ACO:
    """
    ACO sınıfı:
    - Maliyet matrisi (n x n) alır (km, dakika vb. herhangi bir birim).
    - Her iterasyonda belirli sayıda karınca ile en kısa rotayı bulmaya çalışır.
    """

    def __init__(
        self,
        distance_matrix: np.ndarray,
        ant_count: int = 20,
        alpha: float = 1.0,
        beta: float = 3.0,
        rho: float = 0.3,
        Q: float = 100,
        seed: Optional[int] = None,
        start: Optional[int] = 0,
        return_to_start: bool = True,
        elitist_weight: float = 1.0,
        local_search: bool = True,
    ):
        """
        Args:
          - distance_matrix: (n x n) maliyet matrisi. inf değerler "ulaşılamaz" kabul edilir.
          - ant_count: Her iterasyonda kaç karınca kullanılacağı.
          - alpha: Feromon etkisi katsayısı.
          - beta: Mesafe (sezgisel) etkisi katsayısı.
          - rho: Feromon buharlaşma oranı (0 < rho <= 1).
          - Q: Feromon ekleme sabiti (Q / rota uzunluğu).
          - seed: Rastgele sayı üreteci için tohum (isteğe bağlı).
          - start: Sabit başlangıç noktası (depo) indeksi. None ise her karınca rastgele başlar.
          - return_to_start: True ise rota başlangıca geri döner (kapalı tur).
          - elitist_weight: En iyi rotaya eklenen ekstra feromon çarpanı (0 = kapalı).
          - local_search: True ise her iterasyonun en iyi rotasına 2-opt uygulanır.
        """
        D = np.array(distance_matrix, dtype=float, copy=True)
        if D.ndim != 2 or D.shape[0] != D.shape[1]:
            raise ValueError("Mesafe matrisi kare (n x n) olmalıdır.")
        n = D.shape[0]
        if n < 1:
            raise ValueError("En az 1 nokta gereklidir.")
        if start is not None and not (0 <= start < n):
            raise ValueError(f"Başlangıç indeksi geçersiz: {start}")
        if not (0 < rho <= 1):
            raise ValueError("rho (0, 1] aralığında olmalıdır.")
        if ant_count < 1:
            raise ValueError("Karınca sayısı en az 1 olmalıdır.")

        np.fill_diagonal(D, 0.0)
        off_diag = ~np.eye(n, dtype=bool)
        self.unreachable = off_diag & ~np.isfinite(D)
        finite_vals = D[off_diag & np.isfinite(D)]
        max_finite = float(finite_vals.max()) if finite_vals.size else 1.0
        # Ulaşılamayan kenarlar: hiçbir gerçek rotanın geçemeyeceği kadar büyük bir ceza
        self.penalty = max(max_finite, 1.0) * n * 100.0
        D[self.unreachable] = self.penalty
        if (D < 0).any():
            raise ValueError("Mesafe matrisi negatif değer içeremez.")

        self.distances = D
        self.num_nodes = n
        self.ant_count = int(ant_count)
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.rho = float(rho)
        self.Q = float(Q)
        self.start = start
        self.return_to_start = bool(return_to_start)
        self.elitist_weight = float(elitist_weight)
        self.local_search = bool(local_search)
        self.symmetric = bool(np.allclose(D, D.T))
        self.rng = np.random.default_rng(seed)

        # Sezgisel bilgi: (1 / mesafe)^beta. Aynı konumdaki noktalar (mesafe 0) için küçük taban.
        positive = D[off_diag & (D > 0)]
        eps = float(positive.min()) * 1e-3 if positive.size else 1e-9
        with np.errstate(divide="ignore"):
            eta = 1.0 / np.maximum(D, eps)
        np.fill_diagonal(eta, 0.0)
        self.heuristic = eta ** self.beta

        # Başlangıç feromonu: En Yakın Komşu rotasının uzunluğuna göre ölçeklenir
        nn_route = nearest_neighbor(D, start or 0, self.return_to_start)
        nn_len = route_length(D, nn_route) or 1.0
        self.tau0 = self.Q / nn_len
        self.pheromone = np.full((n, n), self.tau0)

        self.iterations_run = 0
        self.runtime_s = 0.0

    # ------------------------------------------------------------------ #
    # Rota oluşturma
    # ------------------------------------------------------------------ #
    def _construct_route(self, weights: np.ndarray) -> List[int]:
        """Bir karınca için olasılıksal rota (kapanış hariç düğüm dizisi) oluşturur."""
        n = self.num_nodes
        start = self.start if self.start is not None else int(self.rng.integers(n))
        visited = np.zeros(n, dtype=bool)
        visited[start] = True
        seq = [start]
        current = start
        for _ in range(n - 1):
            w = np.where(visited, 0.0, weights[current])
            total = w.sum()
            if not np.isfinite(total) or total <= 0:
                nxt = int(self.rng.choice(np.flatnonzero(~visited)))
            else:
                cum = np.cumsum(w)
                nxt = int(np.searchsorted(cum, self.rng.random() * total, side="right"))
                if nxt >= n or visited[nxt]:
                    nxt = int(np.flatnonzero(~visited)[-1])
            seq.append(nxt)
            visited[nxt] = True
            current = nxt
        return seq

    def _close(self, seq: List[int]) -> List[int]:
        return seq + [seq[0]] if self.return_to_start else list(seq)

    def _deposit(self, route: List[int], amount: float) -> None:
        r = np.asarray(route, dtype=int)
        a, b = r[:-1], r[1:]
        np.add.at(self.pheromone, (a, b), amount)
        if self.symmetric:
            np.add.at(self.pheromone, (b, a), amount)

    def _update_pheromones(
        self,
        all_routes: List[List[int]],
        all_lengths: List[float],
        best_route: List[int],
        best_length: float,
    ) -> None:
        """
        Feromon güncellemesi:
          1. Buharlaşma: pheromone *= (1 - rho)
          2. Her karınca rotasına Q / uzunluk kadar feromon
          3. Elitist: en iyi rotaya elitist_weight * Q / en_iyi_uzunluk
        """
        self.pheromone *= (1.0 - self.rho)
        for route, length in zip(all_routes, all_lengths):
            self._deposit(route, self.Q / max(length, 1e-12))
        if self.elitist_weight > 0 and best_route:
            self._deposit(best_route, self.elitist_weight * self.Q / max(best_length, 1e-12))
        # MAX-MIN Ant System sınırları: durgunluğu (stagnation) önler, keşfi sürdürür
        tau_max, tau_min = self._pheromone_bounds(best_length)
        np.clip(self.pheromone, tau_min, tau_max, out=self.pheromone)

    def _pheromone_bounds(self, best_length: float) -> Tuple[float, float]:
        """
        tau_max: tüm karıncalar + elitist aynı kenarı sürekli kullansaydı ulaşılacak denge değeri.
        tau_min: Stützle & Hoos (2000) formülü, p_best = 0.05.
        """
        n = self.num_nodes
        deposit = (self.ant_count + self.elitist_weight) * self.Q / max(best_length, 1e-12)
        tau_max = deposit / self.rho
        p_root = 0.05 ** (1.0 / n)
        avg = max(n / 2.0, 2.0)
        tau_min = tau_max * (1 - p_root) / ((avg - 1) * p_root)
        return tau_max, min(tau_min, tau_max)

    # ------------------------------------------------------------------ #
    # Ana döngü
    # ------------------------------------------------------------------ #
    def run(
        self,
        iterations: int = 100,
        patience: Optional[int] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Tuple[List[int], float, List[Dict]]:
        """
        ACO algoritmasını çalıştırır.
        Args:
          - iterations: En fazla iterasyon (tur) sayısı.
          - patience: Bu kadar iterasyon boyunca iyileşme olmazsa erken durdur (None = kapalı).
          - progress_callback: f(iterasyon, toplam, en_iyi_uzunluk) şeklinde çağrılır.
        Returns:
          - best_route: En iyi rota (kapalı turda başlangıca dönüş dahil).
          - best_length: En iyi rotanın toplam maliyeti.
          - history: Her iterasyon için iteration, best_distance, average_distance, worst_distance.
        """
        t0 = time.perf_counter()
        n = self.num_nodes
        history: List[Dict] = []

        if n <= 2:
            seq = list(range(n))
            if self.start is not None and n == 2 and self.start == 1:
                seq = [1, 0]
            best_route = self._close(seq)
            best_length = route_length(self.distances, best_route)
            history.append({
                "iteration": 1, "best_distance": best_length,
                "average_distance": best_length, "worst_distance": best_length,
            })
            self.iterations_run = 1
            self.runtime_s = time.perf_counter() - t0
            if progress_callback:
                progress_callback(1, 1, best_length)
            return best_route, best_length, history

        best_route: List[int] = []
        best_length = float("inf")
        stale = 0
        fix_start = self.start is not None

        for it in range(1, iterations + 1):
            weights = (self.pheromone ** self.alpha) * self.heuristic
            routes = [self._close(self._construct_route(weights)) for _ in range(self.ant_count)]
            lengths = [route_length(self.distances, r) for r in routes]

            # İterasyonun en iyi rotasını 2-opt ile iyileştir
            ib = int(np.argmin(lengths))
            if self.local_search:
                improved = two_opt(self.distances, routes[ib], self.return_to_start, fix_start)
                improved_len = route_length(self.distances, improved)
                if improved_len < lengths[ib]:
                    routes[ib], lengths[ib] = improved, improved_len

            if lengths[ib] < best_length - 1e-12:
                best_length, best_route = lengths[ib], list(routes[ib])
                stale = 0
            else:
                stale += 1

            self._update_pheromones(routes, lengths, best_route, best_length)

            avg_length = float(np.mean(lengths))
            worst_length = float(np.max(lengths))
            history.append({
                "iteration": it,
                "best_distance": best_length,
                "average_distance": avg_length,
                "worst_distance": worst_length,
            })
            logger.debug(
                "[Iterasyon %d/%d] En İyi=%.3f, Ortalama=%.3f, En Kötü=%.3f",
                it, iterations, best_length, avg_length, worst_length,
            )
            if progress_callback:
                progress_callback(it, iterations, best_length)
            self.iterations_run = it
            if patience is not None and stale >= patience:
                logger.info("Erken durdurma: %d iterasyondur iyileşme yok.", patience)
                break

        # Kapalı turda ve sabit depo yoksa rotayı 0. indeksten başlayacak şekilde döndür
        if self.return_to_start and self.start is None and best_route:
            seq = best_route[:-1]
            k = seq.index(0)
            best_route = self._close(seq[k:] + seq[:k])

        self.runtime_s = time.perf_counter() - t0
        return best_route, best_length, history

    def is_feasible(self, route: List[int]) -> bool:
        """Rota ulaşılamayan (inf) bir kenar kullanmıyorsa True."""
        r = np.asarray(route, dtype=int)
        return not bool(self.unreachable[r[:-1], r[1:]].any())
