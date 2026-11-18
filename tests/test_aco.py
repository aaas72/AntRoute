import numpy as np
import pytest

from aco.algorithm import ACO
from aco.tsp import brute_force, nearest_neighbor, route_length, two_opt
from aco.utils import haversine_distance, haversine_matrix


def random_matrix(n, seed, symmetric=True):
    """Düzlemde rastgele noktalar; asimetrik durumda tek yönlü yolları taklit eden
    yöne bağlı sapma çarpanı (1.0-1.4) uygulanır."""
    rng = np.random.default_rng(seed)
    pts = rng.random((n, 2)) * 10
    d = np.linalg.norm(pts[:, None] - pts[None], axis=-1)
    if not symmetric:
        d = d * rng.uniform(1.0, 1.4, (n, n))
    np.fill_diagonal(d, 0)
    return d


def assert_valid_route(route, n, start, closed):
    if closed:
        assert route[0] == route[-1]
        body = route[:-1]
    else:
        body = route
    assert sorted(body) == list(range(n))
    if start is not None:
        assert route[0] == start


@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("closed", [True, False])
@pytest.mark.parametrize("symmetric", [True, False])
def test_aco_matches_optimum_on_small_instances(seed, closed, symmetric):
    d = random_matrix(8, seed, symmetric)
    opt = route_length(d, brute_force(d, 0, closed))
    aco = ACO(d, ant_count=15, seed=seed, start=0, return_to_start=closed)
    route, length, history = aco.run(iterations=60)
    assert_valid_route(route, 8, 0, closed)
    assert length == pytest.approx(route_length(d, route))
    assert length == pytest.approx(opt, rel=0.02)
    assert len(history) == 60


def test_aco_finds_exact_optimum_in_most_cases():
    hits = 0
    for seed in range(20):
        for closed in (True, False):
            d = random_matrix(8, seed, symmetric=seed % 2 == 0)
            opt = route_length(d, brute_force(d, 0, closed))
            _, length, _ = ACO(d, ant_count=15, seed=seed, return_to_start=closed).run(60)
            hits += abs(length - opt) < 1e-9
    assert hits >= 36  # 40 durumun en az %90'ı


def test_seed_is_deterministic():
    d = random_matrix(15, 1)
    r1 = ACO(d, seed=7, local_search=False).run(30)
    r2 = ACO(d, seed=7, local_search=False).run(30)
    assert r1[0] == r2[0] and r1[1] == r2[1]


def test_does_not_touch_global_numpy_rng():
    np.random.seed(123)
    expected = np.random.random()
    np.random.seed(123)
    ACO(random_matrix(6, 0), seed=1).run(5)
    assert np.random.random() == expected


def test_random_start_closed_tour_starts_at_zero():
    d = random_matrix(10, 3)
    route, _, _ = ACO(d, start=None, seed=0).run(20)
    assert_valid_route(route, 10, 0, True)


def test_custom_depot():
    d = random_matrix(10, 4)
    route, _, _ = ACO(d, start=6, seed=0, return_to_start=False).run(20)
    assert_valid_route(route, 10, 6, False)


def test_unreachable_edges_avoided_when_possible():
    d = random_matrix(6, 2)
    d[0, 1] = d[1, 0] = np.inf
    aco = ACO(d, seed=0)
    route, length, _ = aco.run(40)
    assert aco.is_feasible(route)
    assert np.isfinite(length)


def test_early_stopping():
    d = random_matrix(7, 5)
    aco = ACO(d, seed=0)
    _, _, history = aco.run(500, patience=10)
    assert aco.iterations_run == len(history) < 500


def test_progress_callback_and_best_is_monotonic():
    calls = []
    d = random_matrix(12, 6)
    _, _, history = ACO(d, seed=0).run(25, progress_callback=lambda i, t, b: calls.append((i, t, b)))
    assert [c[0] for c in calls] == list(range(1, 26))
    best = [h["best_distance"] for h in history]
    assert all(a >= b for a, b in zip(best, best[1:]))


@pytest.mark.parametrize("n", [1, 2])
def test_trivial_sizes(n):
    d = random_matrix(n, 0)
    route, length, _ = ACO(d).run(10)
    assert_valid_route(route, n, 0, True)
    assert length == pytest.approx(route_length(d, route))


def test_duplicate_locations_zero_distance():
    d = random_matrix(5, 0)
    d = np.vstack([d, d[2]])
    d = np.hstack([d, d[:, [2]]])
    d[5, 5] = 0
    route, length, _ = ACO(d, seed=0).run(30)
    assert_valid_route(route, 6, 0, True)
    assert np.isfinite(length)


def test_invalid_input():
    with pytest.raises(ValueError):
        ACO(np.zeros((2, 3)))
    with pytest.raises(ValueError):
        ACO(random_matrix(4, 0), start=9)


def test_two_opt_never_worse_than_input_and_fixes_crossing():
    d = random_matrix(20, 9)
    nn = nearest_neighbor(d, 0, True)
    improved = two_opt(d, nn, True)
    assert_valid_route(improved, 20, 0, True)
    assert route_length(d, improved) <= route_length(d, nn)

    # Kare üzerinde çapraz rota: 0-2-1-3 -> 2-opt ile 0-1-2-3
    sq = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
    dsq = np.linalg.norm(sq[:, None] - sq[None], axis=-1)
    assert route_length(dsq, two_opt(dsq, [0, 2, 1, 3, 0])) == pytest.approx(4.0)


def test_two_opt_asymmetric_open_path():
    d = random_matrix(8, 11, symmetric=False)
    start = nearest_neighbor(d, 0, False)
    out = two_opt(d, start, return_to_start=False)
    assert_valid_route(out, 8, 0, False)
    assert route_length(d, out) <= route_length(d, start) + 1e-12


def test_haversine():
    # Elazığ merkez -> Harput (~4-5 km kuş uçuşu)
    km = haversine_distance((38.6748, 39.2225), (38.7066, 39.2577))
    assert 4 < km < 5.5
    m = haversine_matrix([(38.6748, 39.2225), (38.7066, 39.2577)], detour_factor=1.0)
    assert m[0, 1] == pytest.approx(km) and m[0, 0] == 0
