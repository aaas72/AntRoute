"""Gerçek Elâzığ yol ağıyla testler (GraphML dosyası yoksa atlanır)."""
import numpy as np
import pytest

from data.osm_data import GRAPHML_PATH

pytestmark = pytest.mark.skipif(not GRAPHML_PATH.exists(), reason="GraphML yol ağı yok")


@pytest.fixture(scope="module")
def net():
    from data.location_data import load_default_locations
    from data.osm_data import compute_cost_matrices, load_network, snap_to_nodes

    G = load_network()
    coords = list(load_default_locations().values())[:8]
    nodes, snap = snap_to_nodes(G, coords)
    D, T = compute_cost_matrices(G, nodes)
    return G, coords, nodes, snap, D, T


def test_matrices(net):
    _, coords, _, snap, D, T = net
    assert D.shape == T.shape == (len(coords), len(coords))
    assert np.all(np.diag(D) == 0) and np.isfinite(D).all()
    assert (snap < 500).all()
    off = ~np.eye(len(coords), dtype=bool)
    # şehir içi: 0-15 km, ortalama hız makul (10-90 km/sa)
    assert (D[off] > 0).all() and (D[off] < 15).all()
    speed = D[off] / (T[off] / 60)
    assert (speed > 10).all() and (speed < 90).all()


def test_route_legs_follow_roads(net):
    from aco.utils import haversine_matrix
    from data.osm_data import route_legs

    G, coords, nodes, _, D, _ = net
    route = [0, 1, 2, 0]
    legs = route_legs(G, nodes, route)
    straight = haversine_matrix(coords, detour_factor=1.0)
    for leg in legs:
        assert leg["length_km"] == pytest.approx(D[leg["from"], leg["to"]], rel=1e-6)
        assert leg["length_km"] >= straight[leg["from"], leg["to"]] * 0.9
        assert len(leg["coords"]) >= 2
