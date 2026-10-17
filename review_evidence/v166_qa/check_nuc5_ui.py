"""Headless localhost Review QA; intercept Launch so no scan is started."""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path(r'E:\code\bbasm\qa_v166\screens')
out.mkdir(parents=True, exist_ok=True)
base = 'http://127.0.0.1:18767/#/scan/1/review'
captured = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True,
        executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    page = browser.new_page(viewport={'width': 1366, 'height': 768}, device_scale_factor=1)
    page.route('**/api/scans/1/launch', lambda route: (
        captured.append(route.request.post_data_json),
        route.fulfill(status=200, content_type='application/json', body='{"scan_id":1,"status":"queued"}')
    ))
    page.goto(base, wait_until='networkidle')
    page.locator('summary').filter(has_text='Tuỳ chỉnh chi tiết').click()
    page.get_by_text('Tra cứu template theo công nghệ/tag', exact=True).click()
    page.get_by_label('Tag cần tra').fill('bbasmqa')
    page.get_by_role('button', name='Tra cứu', exact=True).click()
    preview = page.get_by_test_id('lookup-total')
    preview.wait_for(timeout=15000)
    preview_text = preview.inner_text()
    rows = page.locator('details:has(summary:text("Tra cứu template theo công nghệ/tag")) table tbody tr').all_inner_texts()
    assert '2 template' in preview_text and any('QA Alpha' in row for row in rows) and any('QA Beta' in row for row in rows), (preview_text, rows)

    page.get_by_role('radio', name=re.compile('^Light')).click()
    toggle = page.get_by_label(re.compile('Tự chọn thêm template theo công nghệ'))
    assert toggle.is_enabled() and not toggle.is_checked()
    toggle.check()
    page.get_by_label(re.compile('Tôi đã đọc policy và program cho phép')).check()
    page.screenshot(path=str(out / 'nuc5_review_1366.png'), full_page=True)
    launch = page.get_by_role('button', name='Launch scan')
    assert launch.is_enabled(), page.locator('.actionbar').inner_text()
    launch.click()
    page.wait_for_timeout(500)
    browser.close()

assert len(captured) == 1 and captured[0]['config']['nuclei_auto_select'] is True, captured
print(json.dumps({'preview': preview_text, 'rows': rows, 'toggle_checked': True,
    'launch_payload': {'nuclei_auto_select': captured[0]['config']['nuclei_auto_select'],
                       'depth': captured[0]['config']['depth'], 'automation_ack': captured[0]['automation_ack']}}, ensure_ascii=True))
