# -*- coding: utf-8 -*-
"""
docs/screenshots.py

Uygulamayı başlatır, Playwright ile gerçek bir tarayıcıda kullanır ve
dokümantasyon görsellerini docs/images/ klasörüne kaydeder.

    pip install playwright && python -m playwright install chromium
    python docs/screenshots.py
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"
PORT = 8611
URL = f"http://localhost:{PORT}"
TILE_WAIT_MS = 6000  # harita karolarının yüklenmesi için

HIDE_CHROME = """
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stStatusWidget"],
[data-testid="stDecoration"] { display: none !important; }
"""


def wait_port(port: int, timeout: float = 60) -> None:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.5)
    raise TimeoutError("Streamlit başlamadı")


def wait_idle(page: Page, extra_ms: int = 500) -> None:
    """Streamlit 'çalışıyor' durumundan çıkana kadar bekle."""
    page.wait_for_timeout(400)
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"stStatusWidget\"] [data-testid=\"stStatusWidgetRunningIcon\"]')"
        " && !document.querySelector('.stSpinner')",
        timeout=180_000,
    )
    page.wait_for_timeout(extra_ms)


def shot_between(page: Page, top_sel, bottom_sel, name: str, pad: int = 16) -> None:
    """İki öğe arasındaki ana alan bölgesini kaydeder."""
    main = page.locator('[data-testid="stMainBlockContainer"]').bounding_box()
    top = top_sel.bounding_box()
    bottom = bottom_sel.bounding_box()
    clip = {
        "x": main["x"],
        "y": max(0, top["y"] - pad),
        "width": main["width"],
        "height": bottom["y"] + bottom["height"] - top["y"] + 2 * pad,
    }
    page.screenshot(path=OUT / name, clip=clip)
    print("✓", name)


def click_button(page: Page, text: str) -> None:
    page.get_by_role("button", name=text).first.click()
    wait_idle(page)


def click_tab(page: Page, tabs, text: str) -> None:
    tabs.get_by_role("tab", name=text).click()
    page.wait_for_timeout(700)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(ROOT / "src" / "ui" / "app.py"),
         "--server.headless", "true", "--server.port", str(PORT),
         "--browser.gatherUsageStats", "false", "--theme.base", "light"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_port(PORT)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 3200}, device_scale_factor=1.5)
            page.goto(URL)
            page.get_by_role("heading", name="AntRoute").wait_for(timeout=60_000)
            page.add_style_tag(content=HIDE_CHROME)
            wait_idle(page, 1000)

            # 1) Durak ekleme
            click_button(page, "Tümünü ekle")
            page.get_by_role("heading", name="2. Rota").wait_for()
            wait_idle(page, 1500)
            stops_h = page.get_by_role("heading", name="1. Teslimat durakları")
            input_tabs = page.locator('[data-testid="stTabs"]').first
            click_tab(page, input_tabs, "Haritadan ekle")
            page.wait_for_timeout(TILE_WAIT_MS)
            run_btn = page.get_by_role("button", name="Optimizasyonu başlat")
            shot_between(page, stops_h, run_btn, "stops.png")

            # 2) Optimizasyon
            run_btn.click()
            page.get_by_role("heading", name="Sonuçlar").wait_for(timeout=180_000)
            wait_idle(page, 1000)
            page.wait_for_timeout(TILE_WAIT_MS)
            results_h = page.get_by_role("heading", name="Sonuçlar")
            tabs = page.locator('[data-testid="stTabs"]').last
            shot_between(page, results_h, tabs, "hero.png")

            for tab, name in [("Rota detayı", "route_details.png"), ("Yakınsama", "convergence.png"),
                              ("Karşılaştırma", "comparison.png"), ("Maliyet matrisi", "cost_matrix.png")]:
                click_tab(page, tabs, tab)
                page.wait_for_timeout(1500)
                tabs.screenshot(path=OUT / name)
                print("✓", name)

            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=20)
    compress()


def compress(max_width: int = 1600) -> None:
    """Görselleri küçültür ve 256 renge indirger (README için makul dosya boyutu)."""
    from PIL import Image

    for f in sorted(OUT.glob("*.png")):
        img = Image.open(f).convert("RGB")
        if img.width > max_width:
            img = img.resize((max_width, round(img.height * max_width / img.width)), Image.LANCZOS)
        img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(
            f, optimize=True)
        print(f"  {f.name}: {f.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
