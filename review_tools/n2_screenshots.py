"""Resolve one H1 handle against a running mock_h1_modes server and screenshot the Review page (desktop 1366px).
  python review_tools/n2_screenshots.py http://127.0.0.1:18770 /path/out.png"""
import json, sys, urllib.request
from playwright.sync_api import sync_playwright
base, out = sys.argv[1], sys.argv[2]
req = urllib.request.Request(base + "/api/scope/resolve", data=json.dumps({"input": "https://hackerone.com/acme?type=team"}).encode(), headers={"Content-Type": "application/json"})
draft = json.load(urllib.request.urlopen(req))
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    page.goto(f"{base}/#/scan/{draft['scan_id']}/review")
    page.wait_for_selector("text=Policy", timeout=15000)
    page.wait_for_timeout(1200)
    page.screenshot(path=out, full_page=True)
    browser.close()
print("saved", out)
