"""Review harness: drives the real UI against mock_h1_server.py (seeded demo-shop) and saves screenshots.
Needs `pip install playwright==1.56.0`, PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers.
  SCR=/tmp/bbasm-mock PYTHONPATH=. python review_tools/mock_h1_server.py &
  SCR=/tmp/bbasm-mock python review_tools/ui_screenshots.py"""
import os
from playwright.sync_api import sync_playwright

S = os.environ.get("SCR", "/tmp/bbasm-mock")
B = os.environ.get("BBASM_URL", "http://127.0.0.1:18766")
os.makedirs(f"{S}/shots", exist_ok=True)

ROUTES = [
    ("01_portfolio", "/#/"),
    ("02_run_done", "/#/scan/2"),
    ("03_overview", "/#/program/demo-shop"),
    ("04_data_urls", "/#/program/demo-shop/data?v=urls"),
    ("05_data_hosts", "/#/program/demo-shop/data?v=hosts"),
    ("06_findings", "/#/program/demo-shop/findings"),
    ("07_history_scans", "/#/program/demo-shop/history?v=scans"),
    ("08_history_diff", "/#/program/demo-shop/history?v=diff"),
    ("09_guide_brief", "/#/program/demo-shop/guide?v=brief"),
    ("10_guide_scope", "/#/program/demo-shop/guide?v=scope"),
    ("11_guide_export", "/#/program/demo-shop/guide?v=export"),
    ("12_help", "/#/help"),
    ("13_profiles", "/#/profiles"),
]


def shot(page, name):
    page.screenshot(path=f"{S}/shots/{name}.png", full_page=True)


with sync_playwright() as p:
    browser = p.chromium.launch()
    for tag, viewport in (("d", {"width": 1366, "height": 850}), ("m", {"width": 390, "height": 800})):
        page = browser.new_page(viewport=viewport)
        for name, route in ROUTES:
            page.goto(B + route)
            page.wait_for_timeout(700)
            shot(page, f"{tag}_{name}")
        page.goto(B + "/#/scan/2")
        page.wait_for_timeout(600)
        page.get_by_role("button", name="Đọc file thô").first.click()
        page.wait_for_timeout(500)
        shot(page, f"{tag}_14_artifact_viewer")
        page.goto(B + "/#/new")
        page.get_by_label("HackerOne handle hoặc URL").fill("https://hackerone.com/acme?type=team")
        page.wait_for_timeout(600)
        page.get_by_role("button", name="Resolve & review").click()
        page.wait_for_url("**/review")
        page.wait_for_timeout(900)
        shot(page, f"{tag}_15_review")
        page.close()
    browser.close()
