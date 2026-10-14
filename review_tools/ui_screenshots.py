"""Review harness: drives the real UI against mock_h1_server.py and saves desktop+mobile screenshots.
Needs `pip install playwright==1.56.0` (matches preinstalled chromium-1194), PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers.
Run mock_h1_server.py first (fresh SCR dir), then: SCR=/tmp/bbasm-mock python review_tools/ui_screenshots.py"""
import os
from playwright.sync_api import sync_playwright

S = os.environ.get("SCR", "/tmp/bbasm-mock")
B = os.environ.get("BBASM_URL", "http://127.0.0.1:18766")
os.makedirs(f"{S}/shots", exist_ok=True)


def shot(page, name):
    page.screenshot(path=f"{S}/shots/{name}.png", full_page=True)


with sync_playwright() as p:
    browser = p.chromium.launch()
    for tag, viewport in (("d", {"width": 1366, "height": 850}), ("m", {"width": 390, "height": 800})):
        page = browser.new_page(viewport=viewport)
        page.goto(B + "/#/")
        page.wait_for_timeout(600)
        shot(page, f"{tag}1_portfolio")
        page.goto(B + "/#/new")
        page.get_by_label("HackerOne handle hoặc URL").fill("https://hackerone.com/acme?type=team")
        page.wait_for_timeout(700)
        shot(page, f"{tag}2_new_h1")
        page.get_by_role("tab", name="Raw scope").click()
        page.get_by_label("Scope — mỗi dòng một asset").fill("*.example.com\n10.0.0.5/24\nbad host!!\n#OUT\nstray")
        page.wait_for_timeout(700)
        shot(page, f"{tag}3_new_raw_errors")
        page.get_by_role("tab", name="HackerOne").click()
        page.get_by_role("button", name="Resolve & review").click()
        page.wait_for_url("**/review")
        page.wait_for_timeout(700)
        shot(page, f"{tag}4_review")
        page.get_by_role("radio", name="Light").click()
        page.get_by_label("Tôi đã đọc policy").check()
        page.get_by_role("button", name="Launch scan").click()
        page.wait_for_function("document.querySelector('[aria-label=\"Scan status\"]')?.innerText.match(/hoàn tất|lỗi/)", timeout=60000)
        page.wait_for_timeout(500)
        shot(page, f"{tag}5_run_done")
        page.goto(B + "/#/program/acme")
        page.wait_for_timeout(800)
        shot(page, f"{tag}6_program_overview")
        for tab in ("Surface", "Assets", "Diff", "Findings", "Brief", "Program"):
            page.get_by_role("tab", name=tab, exact=True).click()
            page.wait_for_timeout(500)
            shot(page, f"{tag}7_{tab.lower()}")
        page.close()
    browser.close()
