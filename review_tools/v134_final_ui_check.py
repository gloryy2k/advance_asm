"""Headless desktop screenshots of completed Wolt Light/Strong and latest data."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path("review_evidence/v134_fixcheck")
base = "http://127.0.0.1:18765"
result = {}
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True,
        executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe")
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    for name, route, marker in (
        ("run_60_light", "/scan/60", "Scan hoàn tất một phần"),
        ("run_64_strong", "/scan/64", "Kết quả theo bước"),
        ("wolt_latest_after_strong", "/program/wolt/data?v=urls", "URL do scan #64"),
    ):
        page.goto(base + "/#" + route, wait_until="domcontentloaded")
        page.get_by_text(marker, exact=False).first.wait_for(timeout=15000)
        if name.startswith("run_"):
            page.get_by_text("Đang tải…", exact=True).wait_for(state="hidden", timeout=15000)
        page.screenshot(path=str(out / (name + ".png")), full_page=True)
        result[name] = {"url": page.url,
                        "horizontal_overflow": page.evaluate("document.documentElement.scrollWidth > innerWidth"),
                        "old_scan_url_links": page.locator('a[href*="scan=60"]').count() if name == "run_60_light" else None}
    browser.close()
print(json.dumps(result, ensure_ascii=True, indent=2))
