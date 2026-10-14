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


@pytest.fixture(scope="module")
def mock_app(tmp_path_factory):
    if not (ROOT / "frontend/dist/index.html").is_file():
        pytest.skip("Build the frontend first: cd frontend && npm run build")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "SCR": str(tmp_path_factory.mktemp("mock")), "MOCK_PORT": str(port)}
    process = subprocess.Popen([sys.executable, str(ROOT / "review_tools/mock_h1_server.py")], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("mock app did not start")
        yield base
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


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
    expect(page.get_by_text("Automated scanning limited to 5 req/s")).to_be_visible()
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
    page.goto(mock_app + "/#/program/acme/program")
    expect(page.get_by_text("Automated scanning limited to 5 req/s")).to_be_visible()
    page.reload()  # tab lives in the URL
    expect(page.get_by_role("tab", name="Program", exact=True)).to_have_attribute("aria-selected", "true")
    # CIDR is one range row, not 254 hosts.
    page.get_by_role("tab", name="Assets", exact=True).click()
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


@pytest.mark.parametrize("route", ["/#/", "/#/new", "/#/program/acme", "/#/program/acme/assets", "/#/program/acme/diff"])
def test_phone_viewport_has_no_horizontal_page_scroll(mock_app, browser, route):
    page = browser.new_page(viewport={"width": 390, "height": 800})
    page.goto(mock_app + route)
    page.wait_for_timeout(600)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), route
    page.close()
