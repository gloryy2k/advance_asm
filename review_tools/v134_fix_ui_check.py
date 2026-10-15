"""Desktop-only, read-only UI check against localhost QA stack; never launches a scan."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:18765"
OUT = Path("review_evidence/v134_fixcheck")
OUT.mkdir(parents=True, exist_ok=True)
result = {}

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe")
    page = browser.new_page(viewport={"width": 1366, "height": 900}, device_scale_factor=1)

    def visit(name, route, terms):
        page.goto(BASE + "/#" + route, wait_until="domcontentloaded")
        for term in terms:
            page.get_by_text(term, exact=False).first.wait_for(timeout=15000)
        page.screenshot(path=str(OUT / (name + ".png")), full_page=True)
        result[name] = {"url": page.url, "terms": terms,
                        "horizontal_overflow": page.evaluate("document.documentElement.scrollWidth > innerWidth")}

    visit("wolt_url_latest", "/program/wolt/data?v=urls", ["Xem URL lịch sử"])
    page.get_by_role("button", name="Xem URL lịch sử").click()
    page.get_by_text("cột “scan”", exact=False).wait_for()
    page.locator("table.urls").wait_for()
    page.screenshot(path=str(OUT / "wolt_url_history.png"), full_page=True)
    result["wolt_url_history"] = {
        "scope_all": page.get_by_label("Phạm vi scan").input_value() == "all",
        "scan_column": "scan" in page.locator("table.urls thead").inner_text().lower(),
        "rows": page.locator("table.urls tbody tr").count(),
        "export_href": page.get_by_role("link", name="Tải danh sách .txt").get_attribute("href"),
    }

    visit("run_31", "/scan/31", ["không phải scan mới nhất", "Xem Brief hiện hành", "Kết quả theo bước"])
    page.get_by_text("Đang tải…", exact=True).wait_for(state="hidden", timeout=15000)
    page.screenshot(path=str(OUT / "run_31.png"), full_page=True)
    result["run_31"].update({"url_links": page.locator('a[href*="scan=31"]').evaluate_all("els => els.map(e => e.getAttribute('href'))"),
                              "brief_link": page.get_by_role("link", name="Xem Brief hiện hành").get_attribute("href")})

    visit("wolt_overview", "/program/wolt", ["trong inventory", "Mỗi lần chạy", "Giám sát liên tục"])
    result["wolt_overview"]["schedule_depth"] = page.get_by_label("Monitoring depth").input_value()
    page.get_by_label("Monitoring depth").select_option("light")
    page.screenshot(path=str(OUT / "wolt_schedule_light.png"), full_page=True)
    result["wolt_schedule_light"] = {"ack_visible": page.get_by_text("Program cho phép scan tự động", exact=False).count() > 0,
                                      "header_notice": page.get_by_text("X-HackerOne-Research", exact=False).count() > 0}

    visit("diff", "/program/qa-v121-diff/history?v=diff", ["Đã so sánh #19 với #17"])
    visit("manual_policy", "/program/qa-v134-ui/guide?v=scope", ["X-HackerOne-Research"])

    # A fake response exercises the reveal control without creating or exposing a real secret.
    def fake_artifact(route):
        reveal = "reveal=true" in route.request.url
        route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "total": 1, "lines": ["H1_TOKEN=FAKE_MARKER" if reveal else "H1_TOKEN=[REDACTED]"],
            "redacted": not reveal,
        }))
    page.route("**/api/scans/31/artifact?**", fake_artifact)
    page.goto(BASE + "/#/scan/31", wait_until="domcontentloaded")
    page.get_by_role("button", name="Đọc file thô", exact=False).first.click()
    box = page.get_by_role("checkbox", name="Hiện giá trị")
    box.wait_for()
    box.check()
    page.get_by_text("FAKE_MARKER", exact=False).wait_for()
    page.screenshot(path=str(OUT / "artifact_reveal_on.png"), full_page=True)
    visible_after_on = box.is_visible() and box.is_checked()
    box.uncheck()
    page.get_by_text("[REDACTED]", exact=False).wait_for()
    page.screenshot(path=str(OUT / "artifact_reveal_off.png"), full_page=True)
    result["artifact_viewer"] = {"control_after_on": visible_after_on,
                                  "control_after_off": box.is_visible() and not box.is_checked()}
    browser.close()

print(json.dumps(result, ensure_ascii=True, indent=2))
