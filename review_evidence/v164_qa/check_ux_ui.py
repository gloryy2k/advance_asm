"""Headless 1366px QA of UX-1 tabs against the localhost fixture stack."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r'E:\code\bbasm\qa_v164\screens')
OUT.mkdir(parents=True, exist_ok=True)
BASE = 'http://127.0.0.1:18766/#/program/example.com/data'

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True,
        executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    page = browser.new_page(viewport={'width': 1366, 'height': 768}, device_scale_factor=1)

    page.goto(BASE + '?v=ports', wait_until='networkidle')
    page.get_by_test_id('ports-partial').wait_for()
    ports = {
        'partial': page.get_by_test_id('ports-partial').inner_text(),
        'cdn': page.get_by_test_id('ports-cdn').inner_text(),
        'rows': page.locator('table tbody tr').count(),
        'title_visible': page.get_by_text('Cổng/Dịch vụ', exact=True).count() > 0,
    }
    page.screenshot(path=str(OUT / 'ports_latest_1366.png'), full_page=True)

    page.goto(BASE + '?v=dirs', wait_until='networkidle')
    page.get_by_test_id('dirs-summary').wait_for()
    dirs = {
        'summary': page.get_by_test_id('dirs-summary').inner_text(),
        'blocked_only': page.get_by_test_id('dirs-blocked-only').inner_text(),
        'rows': page.locator('table tbody tr').count(),
        'title_visible': page.get_by_text('Đường dẫn dò được', exact=True).count() > 0,
    }
    page.screenshot(path=str(OUT / 'dirs_latest_1366.png'), full_page=True)

    page.goto(BASE + '?v=ports&scan=1', wait_until='networkidle')
    page.get_by_test_id('ports-partial').wait_for()
    old_ports = {'rows': page.locator('table tbody tr').count(),
                 'partial_visible': page.get_by_test_id('ports-partial').is_visible()}

    page.goto(BASE + '?v=dirs&scan=1', wait_until='networkidle')
    page.get_by_test_id('dirs-summary').wait_for()
    old_dirs = {'summary': page.get_by_test_id('dirs-summary').inner_text(),
                'rows': page.locator('table tbody tr').count()}
    browser.close()

assert ports['rows'] == 8 and 'DỞ DANG' in ports['partial'] and 'Cloudflare' in ports['cdn']
assert 'chưa chứng minh' in ports['cdn']
assert '35 phản hồi' in dirs['summary'] and '33 giống hệt nhau' in dirs['summary']
assert 'Chỉ có HTTP 403' in dirs['blocked_only'] and dirs['rows'] == 2
print(json.dumps({'ports_latest': ports, 'dirs_latest': dirs,
                  'ports_scan_1': old_ports, 'dirs_scan_1': old_dirs}, ensure_ascii=True))
