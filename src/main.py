#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/main.py

Streamlit uygulamasını başlatır. Hangi klasörden çalıştırıldığı fark etmez:
    python src/main.py
Ek argümanlar Streamlit'e iletilir (ör. python src/main.py --server.port 8502).
"""

import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent / "ui" / "app.py"

if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(APP), *sys.argv[1:]]))
