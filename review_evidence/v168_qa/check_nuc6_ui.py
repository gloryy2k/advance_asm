"""NUC-6 Review QA. Intercept Launch; never start a scan."""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(r'E:\code\bbasm\qa_v168')
out = root / 'screens'
out.mkdir(parents=True, exist_ok=True)
captured = []
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    page = browser.new_page(viewport={'width': 1366, 'height': 768}, device_scale_factor=1)
    page.route('**/api/scans/1/launch', lambda route: (
        captured.append(route.request.post_data_json),
        route.fulfill(status=200, content_type='application/json', body='{"scan_id":1,"status":"queued"}')
    ))
    page.goto('http://127.0.0.1:18768/#/scan/1/review', wait_until='networkidle')
    page.get_by_role('radio', name=re.compile('^Light')).click()
    page.locator('summary').filter(has_text='Tuỳ chỉnh chi tiết').click()
    field = page.get_by_label('nuclei tối đa (giây)')
    assert field.is_visible(), 'NUC-6 timeout field not visible'
    field.fill('45')
    assert field.input_value() == '45'
    page.get_by_label(re.compile('Tôi đã đọc policy và program cho phép')).check()
    page.screenshot(path=str(out / 'nuc6_review_1366.png'), full_page=True)
    launch = page.get_by_role('button', name='Launch scan')
    assert launch.is_enabled(), page.locator('.actionbar').inner_text()
    launch.click()
    page.wait_for_timeout(500)
    browser.close()
assert len(captured) == 1 and captured[0]['config']['nuclei_timeout'] == 45, captured
print(json.dumps({'field_visible': True, 'field_value': '45', 'launch_config_nuclei_timeout': captured[0]['config']['nuclei_timeout'], 'depth': captured[0]['config']['depth'], 'launch_intercepted': True}))
