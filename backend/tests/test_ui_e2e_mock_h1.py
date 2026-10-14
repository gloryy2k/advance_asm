"""Opt-in browser E2E of the guided UX against a *mock* HackerOne (no internet, no recon tools).

Starts review_tools/mock_h1_server.py (real uvicorn + real UI) in a subprocess and drives it with
Chromium. Needs `pip install playwright` + a Chromium; frontend/dist must be built.
Run: pytest -m integration backend/tests/test_ui_e2e_mock_h1.py
"""
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()  # uvicorn can wait on an open WebSocket; the harness must never hang the suite
        process.wait(timeout=5)


def launch(tmp_path_factory, seed):
    if not (ROOT / "frontend/dist/index.html").is_file():
        pytest.skip("Build the frontend first: cd frontend && npm run build")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "SCR": str(tmp_path_factory.mktemp("mock")), "MOCK_PORT": str(port), "SEED_DEMO": seed, "PYTHONPATH": str(ROOT)}
    process = subprocess.Popen([sys.executable, str(ROOT / "review_tools/mock_h1_server.py")], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1)
            return process, base
        except OSError:
            time.sleep(0.1)
    process.terminate()
    pytest.fail("mock app did not start")


@pytest.fixture(scope="module")
def mock_app(tmp_path_factory):
    """Empty install: the first-run experience."""
    process, base = launch(tmp_path_factory, "0")
    yield base
    stop(process)


@pytest.fixture(scope="module")
def seeded_app(tmp_path_factory):
    """A finished program (demo-shop: 2 completed scans, URLs, a finding) to look at results."""
    process, base = launch(tmp_path_factory, "1")
    yield base
    stop(process)


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.mark.skipif(os.name != "posix", reason="Needs a Linux/WSL2/Docker backend: native Windows cannot run recon")
def test_h1_flow_policy_gate_launch_and_program_md(mock_app, browser):
    from playwright.sync_api import expect
    page = browser.new_page(viewport={"width": 1366, "height": 850})
    page.goto(mock_app + "/#/")
    expect(page.get_by_text("Chưa có program nào")).to_be_visible()
    page.get_by_role("link", name="Thêm program đầu tiên").click()
    page.get_by_label("HackerOne handle hoặc URL").fill("https://hackerone.com/acme?type=team")
    expect(page.get_by_text("Nhận diện: program")).to_be_visible()
    page.get_by_role("button", name="Resolve & review").click()
    # Review: policy + OUT + CIDR size + manual asset are visible BEFORE anything runs.
    expect(page.get_by_text("Automated scanning limited to 5 req/s").first).to_be_visible()
    expect(page.get_by_text("CHƯA XÁC MINH").or_(page.get_by_text("Đã lấy qua API HackerOne")).first).to_be_visible()
    expect(page.get_by_text("256 địa chỉ")).to_be_visible()
    expect(page.get_by_role("group", name=re.compile("Loại trừ")).get_by_text("legacy.acme.com")).to_be_visible()
    expect(page.get_by_text("Mobile — làm tay")).to_be_visible()
    launch = page.get_by_role("button", name="Launch scan")
    expect(launch).to_be_disabled()  # default Light needs the automation confirmation
    page.get_by_label(re.compile("Tôi đã đọc policy")).check()
    expect(launch).to_be_enabled()
    launch.click()
    expect(page.get_by_role("status", name="Scan status")).to_have_text(re.compile("hoàn tất"), timeout=90000)
    expect(page.get_by_text(re.compile(r'cd ".*acme" && claude'))).to_be_visible()
    # Policy fetched from H1 reached the durable PROGRAM.md (F1 regression, end to end).
    page.goto(mock_app + "/#/program/acme/guide?v=instructions")
    expect(page.get_by_text("Automated scanning limited to 5 req/s").first).to_be_visible()
    page.reload()  # area and view live in the URL
    expect(page.get_by_role("tab", name="Hướng dẫn & scope", exact=True)).to_have_attribute("aria-selected", "true")
    expect(page.get_by_role("tab", name="Hướng dẫn cho agent")).to_have_attribute("aria-selected", "true")
    # CIDR is one range row, not 254 hosts.
    page.goto(mock_app + "/#/program/acme/data?v=hosts")
    expect(page.get_by_text("198.51.100.0/24")).to_be_visible()
    assert page.locator("tbody tr").count() <= 5
    page.close()


def test_raw_scope_cannot_silently_flip_out_to_in(mock_app, browser):
    from playwright.sync_api import expect
    page = browser.new_page()
    page.goto(mock_app + "/#/new")
    page.get_by_role("tab", name="Raw scope").click()
    page.get_by_label("Scope — mỗi dòng một asset").fill("a.example.com\n# OUTT\nsecret.example.com")
    expect(page.get_by_text("Giống header OUT nhưng sai cú pháp")).to_be_visible()
    expect(page.get_by_role("button", name="Resolve & review")).to_be_disabled()
    page.get_by_label("Scope — mỗi dòng một asset").fill("a.example.com\n# OUT\nsecret.example.com")
    expect(page.get_by_role("button", name="Resolve & review")).to_be_enabled()
    page.close()


def test_results_are_explained_step_by_step_and_openable(seeded_app, browser):
    from playwright.sync_api import expect
    page = browser.new_page(viewport={"width": 1366, "height": 850})
    page.goto(seeded_app + "/#/scan/2")
    steps = page.locator("li.step")
    expect(steps).to_have_count(12)
    probe = page.locator('li.step[data-step="live_probe"]')
    expect(probe).to_contain_text("Đã chạy")
    expect(probe).to_contain_text("chạm target")  # says whether it touches the target
    expect(page.locator('li.step[data-step="port_scan"]')).to_contain_text("Bỏ qua")
    expect(page.locator('li.step[data-step="nuclei"]').get_by_role("link", name=re.compile("Xem findings"))).to_be_visible()
    # raw output opens in a viewer with search
    page.locator('li.step[data-step="url_history"]').get_by_role("button", name=re.compile("Đọc file thô")).click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("shop.example.com/api/v1/users?id=12")
    dialog.get_by_label("Tìm trong file").fill("login")
    expect(dialog.locator("ol.lines li")).to_have_count(1)
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)
    page.close()


def test_url_explorer_funnel_default_filter_and_export(seeded_app, browser):
    from playwright.sync_api import expect
    page = browser.new_page(viewport={"width": 1366, "height": 850})
    page.goto(seeded_app + "/#/program/demo-shop/data?v=urls")
    funnel = page.get_by_label("Phễu URL")
    expect(funnel).to_contain_text("52")
    expect(funnel).to_contain_text("49")
    expect(page.get_by_text("Đang ẩn")).to_contain_text("42")  # plain pages (39 products + 3 hosts) hidden by default, and it says so
    expect(page.locator("table.urls tbody tr").first).to_contain_text("/api/v1/")  # best first
    page.get_by_role("button", name=re.compile(r"^API\s*3")).click()
    expect(page.locator("table.urls tbody tr")).to_have_count(3)
    expect(page.get_by_text("đã crawl").first).to_be_visible()
    expect(page.get_by_text("lịch sử", exact=True).first).to_be_visible()
    href = page.get_by_role("link", name=re.compile("Tải danh sách")).get_attribute("href")
    assert "tag=api" in href
    text = page.request.get(seeded_app + href).text()
    assert text.strip().splitlines()[0].startswith("https://shop.example.com/api/")
    page.close()


def test_every_area_loads_and_overview_points_somewhere(seeded_app, browser):
    from playwright.sync_api import expect
    page = browser.new_page(viewport={"width": 1366, "height": 850})
    page.goto(seeded_app + "/#/program/demo-shop")
    expect(page.get_by_role("tab")).to_have_count(5)
    expect(page.get_by_text("Việc nên làm tiếp")).to_be_visible()
    page.get_by_role("tab", name="Lịch sử").click()
    page.get_by_role("tab", name="So sánh thay đổi").click()
    expect(page.get_by_text("so với scan hoàn tất gần nhất trước đó (#1)")).to_be_visible()
    expect(page.get_by_text("THAY ĐỔI").first).to_be_visible()  # Passive -> Light shows status/tech changes
    page.get_by_role("tab", name="Hướng dẫn & scope").click()
    expect(page.get_by_label("AGENT_BRIEF.md")).to_contain_text("ENDPOINT ĐÁNG XEM")
    page.get_by_role("tab", name="Xuất ZIP").click()
    expect(page.get_by_role("link", name="Tải ZIP ↓")).to_have_count(3)
    page.goto(seeded_app + "/#/help")
    expect(page.get_by_role("heading", name="Chức năng & kết quả")).to_be_visible()
    assert page.locator("table tbody tr").count() >= 12
    page.close()


def test_customise_steps_and_save_profile(seeded_app, browser):
    from playwright.sync_api import expect
    page = browser.new_page(viewport={"width": 1366, "height": 850})
    page.goto(seeded_app + "/#/program/demo-shop")
    page.get_by_role("button", name="Scan lại").click()
    page.wait_for_url("**/review")
    expect(page.get_by_text("Đang đúng theo preset Light")).to_be_visible()
    page.get_by_label("Chạy: Takeover").uncheck()
    page.get_by_text("Tuỳ chỉnh chi tiết").click()
    page.get_by_label(re.compile("^Số luồng")).fill("120")
    expect(page.get_by_text(re.compile("Khác preset Light"))).to_contain_text("2 mục")
    page.get_by_role("button", name=re.compile("Lưu cấu hình này thành profile")).click()
    page.get_by_label("Tên profile").fill("Nhanh")
    page.get_by_role("button", name="Lưu", exact=True).click()
    expect(page.get_by_text("Đang đúng theo preset Nhanh")).to_be_visible()
    page.goto(seeded_app + "/#/profiles")
    expect(page.locator("ul.profiles li", has_text="Nhanh")).to_contain_text("120 luồng")
    page.close()


@pytest.mark.parametrize("route", ["/#/", "/#/new", "/#/scan/2", "/#/program/demo-shop", "/#/program/demo-shop/data?v=urls",
                                   "/#/program/demo-shop/data?v=hosts", "/#/program/demo-shop/history?v=diff", "/#/program/demo-shop/guide?v=brief",
                                   "/#/help", "/#/profiles"])
def test_phone_viewport_has_no_horizontal_page_scroll(seeded_app, browser, route):
    page = browser.new_page(viewport={"width": 390, "height": 800})
    page.goto(seeded_app + route)
    page.wait_for_timeout(700)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), route
    page.close()


def test_review_on_phone_keeps_the_launch_button_reachable(seeded_app, browser):
    from playwright.sync_api import expect
    page = browser.new_page(viewport={"width": 390, "height": 800})
    page.goto(seeded_app + "/#/program/demo-shop")
    page.get_by_role("button", name="Scan lại").click()
    page.wait_for_url("**/review")
    launch = page.get_by_role("button", name="Launch scan")
    expect(launch).to_be_visible()  # fixed action bar: visible without scrolling the whole page
    box = launch.bounding_box()
    assert box and box["y"] + box["height"] <= 800 and box["x"] >= 0
    page.close()
