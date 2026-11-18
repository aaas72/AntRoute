import io
from urllib.parse import parse_qs, urlparse

import pytest

from data.location_data import load_locations_from_csv
from ui.export import GMAPS_MAX_STOPS, format_minutes, google_maps_links, route_table


def test_csv_aliases_semicolon_and_duplicates():
    csv = "Ad;Enlem;Boylam\nDepo;38,67;39,22\nDepo;38.68;39.23\n;38.69;39.24\n"
    locs = load_locations_from_csv(io.StringIO(csv))
    assert list(locs) == ["Depo", "Depo (2)", "Nokta 3"]
    assert locs["Depo"] == (38.67, 39.22)


@pytest.mark.parametrize("csv", ["name,latitude\nA,1\n", "name,latitude,longitude\nA,99,1\n",
                                 "name,latitude,longitude\nA,abc,1\n"])
def test_csv_errors(csv):
    with pytest.raises(ValueError):
        load_locations_from_csv(io.StringIO(csv))


def test_format_minutes():
    assert format_minutes(7.4) == "7 dk"
    assert format_minutes(65) == "1 sa 05 dk"
    assert format_minutes(float("inf")) == "—"


def test_google_maps_links_split_long_routes():
    coords = [(38.6 + i / 100, 39.2) for i in range(25)]
    route = list(range(25)) + [0]
    links = google_maps_links(coords, route)
    assert len(links) == 3
    stops = 0
    for url in links:
        q = parse_qs(urlparse(url).query)
        n = 2 + len(q.get("waypoints", [""])[0].split("|")) if "waypoints" in q else 2
        assert n <= GMAPS_MAX_STOPS
        stops += n
    # parçalar uç noktaları paylaşır
    assert parse_qs(urlparse(links[0]).query)["destination"] == parse_qs(urlparse(links[1]).query)["origin"]
    assert parse_qs(urlparse(links[-1]).query)["destination"][0] == "38.600000,39.200000"


def test_route_table_cumulative():
    legs = [{"from": 0, "to": 1, "length_km": 1.0, "time_min": 2.0},
            {"from": 1, "to": 0, "length_km": 1.5, "time_min": 3.0}]
    df = route_table(["A", "B"], [(0, 0), (1, 1)], [0, 1, 0], legs)
    assert df["Toplam (km)"].tolist() == [1.0, 2.5]
    assert df["Nereye"].tolist() == ["B", "A"]
