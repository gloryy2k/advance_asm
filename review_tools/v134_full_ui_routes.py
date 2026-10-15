"""Read-only desktop smoke of BBASM localhost; no launch or mutation."""
import json
from playwright.sync_api import sync_playwright

base = "http://127.0.0.1:18765/#"
routes = [
    "/", "/new", "/profiles", "/help", "/program/wolt",
    "/program/wolt/data?v=urls", "/program/wolt/data?v=hosts",
    "/program/wolt/data?v=surface", "/program/wolt/findings",
    "/program/wolt/history?v=scans", "/program/wolt/history?v=diff",
    "/program/wolt/guide?v=brief", "/program/wolt/guide?v=instructions",
    "/program/wolt/guide?v=scope", "/program/wolt/guide?v=export",
    "/scan/59", "/scan/57/review",
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe")
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)[:200]))
    rows = []
    for route in routes:
        errors.clear()
        responses = []
        handler = lambda r: responses.append({"status": r.status, "path": r.url.split("?", 1)[0].split("/api/")[-1]}) if "/api/" in r.url and r.status >= 400 else None
        page.on("response", handler)
        page.goto(base + route, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(450)
        rows.append({
            "route": route,
            "main_chars": len(page.locator("main").inner_text()),
            "h1": page.locator("main h1").first.inner_text() if page.locator("main h1").count() else "",
            "overflow_px": page.evaluate("document.documentElement.scrollWidth-innerWidth"),
            "error_boxes": page.locator(".error").count(),
            "js_errors": list(errors), "api_errors": responses,
        })
        page.remove_listener("response", handler)
    browser.close()
print(json.dumps(rows, ensure_ascii=True))
