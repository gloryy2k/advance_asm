"""Wolt/v1.3 host QA: nuclei was "available" with 0 templates, so scans said "no findings" after testing nothing."""
import os
import stat

import pytest
from fastapi.testclient import TestClient

from backend.asm.phases import PHASES, build_report, plan_for, tools_needed
from backend.jobs.recon_orch import ReconOrchestrator, nuclei_templates_ready
from backend.main import create_app
from backend.tests.p2_helpers import environment


@pytest.fixture
def home(tmp_path, monkeypatch):
    (tmp_path / "go" / "bin").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", f"{tmp_path / 'go' / 'bin'}:/usr/bin:/bin")
    nuclei = tmp_path / "go" / "bin" / "nuclei"
    nuclei.write_text("#!/bin/sh\nexit 0\n")
    nuclei.chmod(nuclei.stat().st_mode | stat.S_IEXEC)
    return tmp_path


def add_template(home):
    path = home / "nuclei-templates" / "http" / "exposures"
    path.mkdir(parents=True)
    (path / "demo.yaml").write_text("id: demo\n")


def test_a_binary_without_templates_is_reported_missing_everywhere(home, settings):
    assert not nuclei_templates_ready(settings)
    missing = ReconOrchestrator(settings, None).missing_tools()
    assert "nuclei" not in missing and "nuclei-templates" in missing
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/health").json()
    assert body["tools"]["nuclei"] is True and body["tools"]["nuclei-templates"] is False
    assert "nuclei-templates" in body["missing_by_depth"]["light"]
    add_template(home)
    assert nuclei_templates_ready(settings) and "nuclei-templates" not in ReconOrchestrator(settings, None).missing_tools()


def test_review_plan_marks_nuclei_as_missing_instead_of_on(home, settings):
    db, _, result = environment(settings, ["example.com"])
    config = result.config.model_copy(update={"depth": "light", "skip_nuclei": False})
    plan = {p["key"]: p for p in plan_for(config, settings, ["nuclei-templates"])}
    assert plan["nuclei"]["status"] == "missing_tool" and "nuclei-templates" in plan["nuclei"]["reason"]
    assert {p["key"]: p for p in plan_for(config, settings, [])}["nuclei"]["status"] == "on"
    assert "nuclei-templates" in tools_needed(config, settings)                      # so the run warns about it
    assert "nuclei-templates" not in tools_needed(config.model_copy(update={"skip_nuclei": True}), settings)


def test_run_report_does_not_present_a_templateless_nuclei_as_no_findings(home, settings):
    import json
    db, _, result = environment(settings, ["example.com"])
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='done', stats_json=? WHERE id=?",
                     (json.dumps({"missing_tools": ["nuclei-templates"], "resolved_scope": []}), result.scan_id))
        conn.execute("UPDATE scan_config SET depth='light', skip_nuclei=0 WHERE scan_run_id=?", (result.scan_id,))
    report = build_report(settings, db, result.scan_id)
    nuclei = next(p for p in report["phases"] if p["key"] == "nuclei")
    assert nuclei["status"] == "missing_tool" and "không kiểm tra gì" in nuclei["reason"]
    assert next(p for p in PHASES if p["key"] == "nuclei")["all_required"] is True
