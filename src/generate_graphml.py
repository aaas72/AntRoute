# -*- coding: utf-8 -*-
"""
generate_graphml.py

Elâzığ yol ağını OpenStreetMap'ten indirir (hız ve seyahat süresi bilgisiyle)
ve src/data/elazig_osm.graphml dosyasına kaydeder. Yalnızca bir kez çalıştırın.

Kullanım:
    python src/generate_graphml.py                       # merkez etrafında 9 km
    python src/generate_graphml.py --radius 12000
    python src/generate_graphml.py --place "Merkez, Elazığ, Türkiye"
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data.osm_data import (  # noqa: E402
    DEFAULT_CENTER, DEFAULT_RADIUS_M, GRAPHML_PATH, download_network,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Elâzığ OSM yol ağını indir.")
    parser.add_argument("--lat", type=float, default=DEFAULT_CENTER[0], help="Merkez enlemi")
    parser.add_argument("--lon", type=float, default=DEFAULT_CENTER[1], help="Merkez boylamı")
    parser.add_argument("--radius", type=int, default=DEFAULT_RADIUS_M, help="Yarıçap (metre)")
    parser.add_argument("--place", type=str, default=None, help="Yer adı (yarıçap yerine)")
    parser.add_argument("--network-type", default="drive", help="drive, bike, walk ...")
    parser.add_argument("--output", type=Path, default=GRAPHML_PATH, help="Çıktı dosyası")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = download_network(
        center=(args.lat, args.lon),
        radius_m=args.radius,
        path=args.output,
        network_type=args.network_type,
        place=args.place,
    )
    print(f"Başarıyla kaydedildi: {path}")


if __name__ == "__main__":
    main()
