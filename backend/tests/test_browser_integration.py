"""Opt-in TC-FE-6 on an already-running Linux/Docker app and authorized target."""
import os
import re

import pytest

pytestmark = pytest.mark.integration


def test_browser_resolve_review_launch_to_brief():
    target = os.environ.get("BBASM_E2E_TARGET")
    if not target:
        pytest.skip("Set BBASM_E2E_TARGET to an authorized domain; real recon required")
    sync_api = pytest.importorskip("playwright.sync_api")
    base = os.environ.get("BBASM_E2E_URL", "http://127.0.0.1:8000")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(base + "/#/new")
            page.get_by_role("tab", name="Raw scope").click()
            page.get_by_label("Scope — mỗi dòng một asset").fill(target)
            page.get_by_role("button", name="Resolve & review").click()
            page.get_by_role("radio", name=re.compile("Passive")).click()
            page.get_by_role("button", name="Launch scan").click()
            sync_api.expect(page.get_by_role("status", name="Scan status")).to_have_text("hoàn tất", timeout=360000)
            page.goto(base + "/#/")
            page.get_by_role("heading", name=target, exact=True).click()
            page.get_by_role("tab", name="Brief", exact=True).click()
            sync_api.expect(page.get_by_label("AGENT_BRIEF.md")).to_contain_text("# AGENT BRIEF")
        finally:
            browser.close()
