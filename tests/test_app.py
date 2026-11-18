"""Streamlit arayüzünün uçtan uca (headless) testi."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "src" / "ui" / "app.py")


def _app():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    assert not at.exception, at.exception
    return at


def _add_defaults(at, k):
    at.multiselect[0].set_value(at.multiselect[0].options[:k]).run()
    next(b for b in at.button if "Seçilenleri ekle" in b.label).click().run()
    assert not at.exception, at.exception


def _run(at):
    next(b for b in at.button if "Optimizasyonu başlat" in b.label).click().run()
    assert not at.exception, at.exception
    return at.session_state.results


def test_empty_state_asks_for_stops():
    at = _app()
    assert any("en az 2 durak" in i.value for i in at.info)


@pytest.mark.parametrize("use_network", [False, True])
def test_full_run(use_network):
    at = _app()
    toggle = [t for t in at.toggle if "yol ağı" in t.label]
    if use_network and not toggle:
        pytest.skip("GraphML yol ağı dosyası yok")
    if toggle:
        toggle[0].set_value(use_network).run()
    _add_defaults(at, 6)
    res = _run(at)
    assert res is not None
    assert len(res["names"]) == 6
    assert res["route"][0] == res["route"][-1] == 0
    assert res["optimum"] is not None
    assert res["best_cost"] == pytest.approx(res["optimum"])
    assert any("Toplam mesafe" in m.label for m in at.metric)


def test_open_route_with_custom_depot_and_time_objective():
    at = _app()
    _add_defaults(at, 12)
    at.radio[0].set_value("time").run()          # kriter: süre
    at.selectbox[0].set_value(3).run()           # depo: 4. durak
    next(t for t in at.toggle if "geri dön" in t.label).set_value(False).run()
    res = _run(at)
    assert res["route"][0] == 3 and res["route"][-1] != 3
    assert sorted(res["route"]) == list(range(12))
    assert res["cfg"]["objective"] == "time"
    assert res["optimum"] is None  # 12 > kaba kuvvet sınırı
