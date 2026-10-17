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
    assert nuclei["status"] == "missing_tool" and "không được chạy" in nuclei["reason"]
    assert next(p for p in PHASES if p["key"] == "nuclei")["all_required"] is True


FAKE_NUCLEI = """#!/bin/bash
printf '%s\\n' "$@" > "$(dirname "$0")/nuclei.argv"
"""


def run_shim(home, *args, extra_env=None):
    import subprocess
    from backend.jobs.recon_orch import SHIM_DIR
    out = home / "out"
    out.mkdir(exist_ok=True)
    env = {"PATH": f"{home / 'go' / 'bin'}:/usr/bin:/bin", "HOME": str(home), "RECON_OUT_DIR": str(out), **(extra_env or {})}
    subprocess.run([str(SHIM_DIR / "nuclei"), *args], env=env, check=True, timeout=20)
    return out


def test_nuclei_wrapper_never_starts_nuclei_without_templates(home):
    (home / "go" / "bin" / "nuclei").write_text(FAKE_NUCLEI)
    from backend.jobs.recon_orch import read_tool_notes
    out = run_shim(home, "-l", "hosts.txt", "-severity", "low")
    assert not (home / "go" / "bin" / "nuclei.argv").exists()                      # nothing was executed, so nothing was downloaded
    assert read_tool_notes(out)[0]["tool"] == "nuclei" and "chặn" in read_tool_notes(out)[0]["note"]


def test_nuclei_wrapper_starts_nuclei_with_the_update_check_disabled_when_templates_exist(home):
    (home / "go" / "bin" / "nuclei").write_text(FAKE_NUCLEI)
    add_template(home)
    run_shim(home, "-l", "hosts.txt", "-severity", "low")
    argv = (home / "go" / "bin" / "nuclei.argv").read_text().split()
    # no update check, and the dangerous template tags are left out unless the user opted in
    assert argv[:3] == ["-duc", "-etags", "dos,fuzz,intrusive,bruteforce,brute-force"] and argv[3:] == ["-l", "hosts.txt", "-severity", "low"]
    run_shim(home, "-duc", "-l", "x")
    assert (home / "go" / "bin" / "nuclei.argv").read_text().split().count("-duc") == 1   # never doubled
    run_shim(home, "-etags", "mine", "-l", "x")
    assert (home / "go" / "bin" / "nuclei.argv").read_text().split().count("-etags") == 1   # an explicit choice is not overridden


def test_the_scan_says_plainly_that_nuclei_was_blocked_not_that_it_ran(home, settings):
    """v1.3.2 host QA (P2): the run page must not read as if nuclei ran and found nothing."""
    from backend.jobs.recon_orch import NUCLEI_BLOCKED_NOTE
    db, _, result = environment(settings, ["example.com"])
    from backend.jobs.runner import JobRunner
    JobRunner(settings, db).config(result.scan_id, result.config.model_copy(update={"depth": "light", "skip_nuclei": False}))
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    assert plan.tool_notes == [{"tool": "nuclei", "note": NUCLEI_BLOCKED_NOTE}]
    assert "KHÔNG được chạy" in NUCLEI_BLOCKED_NOTE and "chặn" in NUCLEI_BLOCKED_NOTE
    assert plan.commands[0].env["BBASM_SKIP_NUCLEI"] == "1"
    # With templates, or with nuclei switched off, there is nothing to explain.
    add_template(home)
    new = __import__("backend.jobs.scope_resolver", fromlist=["ScopeResolver"]).ScopeResolver(settings, db, __import__("unittest.mock", fromlist=["Mock"]).Mock()).resolve(
        __import__("backend.models", fromlist=["ResolveRequest"]).ResolveRequest(input="raw", scope=["example.com"], name="second"))
    JobRunner(settings, db).config(new.scan_id, new.config.model_copy(update={"depth": "light", "skip_nuclei": False}))
    assert ReconOrchestrator(settings, db).build(new.scan_id).tool_notes == []


def test_intrusive_templates_come_back_only_when_the_user_opts_in(home):
    (home / "go" / "bin" / "nuclei").write_text(FAKE_NUCLEI)
    add_template(home)
    run_shim(home, "-l", "x", extra_env={"BBASM_NUCLEI_ALLOW_INTRUSIVE": "1"})
    assert "-etags" not in (home / "go" / "bin" / "nuclei.argv").read_text().split()


def test_auto_select_adds_as_and_vv_and_captures_what_was_loaded(home):
    (home / "go" / "bin" / "nuclei").write_text(FAKE_NUCLEI)
    add_template(home)
    out = run_shim(home, "-l", "x", extra_env={"BBASM_NUCLEI_AUTO_SELECT": "1"})
    argv = (home / "go" / "bin" / "nuclei.argv").read_text().split()
    assert "-as" in argv and "-vv" in argv
    from backend.jobs.recon_orch import read_tool_notes
    notes = [n["note"] for n in read_tool_notes(out) if n["tool"] == "nuclei"]
    assert any("-as" in n for n in notes)
    # FAKE_NUCLEI writes nothing to its own stdout, but the shim must still redirect it to templates_loaded.txt
    # when $RECON_OUT_DIR/nuclei exists (recon_engine.sh's own Phase 9 creates it before calling nuclei).
    (out / "nuclei").mkdir()
    run_shim(home, "-l", "x", extra_env={"BBASM_NUCLEI_AUTO_SELECT": "1"})
    assert (out / "nuclei" / "templates_loaded.txt").is_file()


def test_auto_select_syncs_the_managed_set_into_home_when_they_differ(home, tmp_path):
    """V166_HOST_AUDIT.md P1: nuclei's -as always reads $HOME/nuclei-templates (hardcoded, ignores -t, does not
    follow a symlink there either) to build its tech-detection service; without a real directory there it fails
    outright instead of just skipping auto-select. The shim must keep a real (hard-linked) copy in sync."""
    (home / "go" / "bin" / "nuclei").write_text(FAKE_NUCLEI)
    official = tmp_path / "official"
    (official / "http" / "technologies").mkdir(parents=True)
    (official / "http" / "technologies" / "tech-detect.yaml").write_text("id: tech-detect\n")
    assert not (home / "nuclei-templates").exists()        # the managed set lives elsewhere, not at the default path
    run_shim(home, "-l", "x", extra_env={"BBASM_NUCLEI_OFFICIAL": str(official), "BBASM_NUCLEI_AUTO_SELECT": "1"})
    synced = home / "nuclei-templates" / "http" / "technologies" / "tech-detect.yaml"
    assert synced.is_file() and not synced.is_symlink() and synced.read_text() == "id: tech-detect\n"
    # a second run (the set may have been updated between scans) keeps it in sync, not just created once
    (official / "http" / "technologies" / "tech-detect.yaml").write_text("id: tech-detect-v2\n")
    run_shim(home, "-l", "x", extra_env={"BBASM_NUCLEI_OFFICIAL": str(official), "BBASM_NUCLEI_AUTO_SELECT": "1"})
    assert synced.read_text() == "id: tech-detect-v2\n"


def test_auto_select_does_not_resync_when_official_already_is_the_default_path(home):
    """The common case (no separate managed dir, templates already at $HOME/nuclei-templates) needs no copy."""
    (home / "go" / "bin" / "nuclei").write_text(FAKE_NUCLEI)
    add_template(home)
    marker = home / "nuclei-templates" / ".marker"
    marker.write_text("untouched")
    run_shim(home, "-l", "x", extra_env={"BBASM_NUCLEI_AUTO_SELECT": "1"})
    assert marker.read_text() == "untouched"                # not wiped/recreated


FAKE_NUCLEI_WITH_FINDING_ECHO = """#!/bin/bash
printf '%s\\n' "$@" > "$(dirname "$0")/nuclei.argv"
echo '[demo-check] Demo (@me) [info]'
echo '{"template-id":"demo-check","host":"a.example.com","matched-at":"https://a.example.com/"}'
echo '[other-check] Other (@me) [low]'
"""


def test_auto_select_strips_finding_jsonl_echoed_to_stdout_from_the_template_list(home):
    """V166_HOST_AUDIT.md P3: nuclei echoes each finding's full JSONL record to stdout too, interleaved on the SAME
    stream as -vv's own "[id] Name (@author) [severity]" lines. templates_loaded.txt must only be the template
    list it claims to be; findings.jsonl (via -o) stays the one place findings are read from."""
    (home / "go" / "bin" / "nuclei").write_text(FAKE_NUCLEI_WITH_FINDING_ECHO)
    add_template(home)
    out = run_shim(home, "-l", "x", extra_env={"BBASM_NUCLEI_AUTO_SELECT": "1"})
    (out / "nuclei").mkdir()
    run_shim(home, "-l", "x", extra_env={"BBASM_NUCLEI_AUTO_SELECT": "1"})
    lines = (out / "nuclei" / "templates_loaded.txt").read_text().splitlines()
    assert lines == ["[demo-check] Demo (@me) [info]", "[other-check] Other (@me) [low]"]
    assert not any(line.startswith("{") for line in lines)


def test_auto_select_is_off_by_default_and_an_explicit_as_is_not_doubled(home):
    (home / "go" / "bin" / "nuclei").write_text(FAKE_NUCLEI)
    add_template(home)
    run_shim(home, "-l", "x")
    assert "-as" not in (home / "go" / "bin" / "nuclei.argv").read_text().split()
    run_shim(home, "-as", "-l", "x", extra_env={"BBASM_NUCLEI_AUTO_SELECT": "1"})
    assert (home / "go" / "bin" / "nuclei.argv").read_text().split().count("-as") == 1


def test_shim_points_nuclei_at_the_managed_set_and_the_chosen_custom_templates(home, tmp_path):
    (home / "go" / "bin" / "nuclei").write_text(FAKE_NUCLEI)
    official = tmp_path / "official"
    (official / "http").mkdir(parents=True)
    (official / "http" / "a.yaml").write_text("id: a\n")
    custom = tmp_path / "mine.yaml"
    custom.write_text("id: mine\n")
    run_shim(home, "-l", "x", extra_env={"BBASM_NUCLEI_OFFICIAL": str(official), "BBASM_NUCLEI_CUSTOM": f"{custom}\n/does/not/exist.yaml"})
    argv = (home / "go" / "bin" / "nuclei.argv").read_text().split()
    pairs = [argv[i + 1] for i, a in enumerate(argv) if a == "-t"]
    assert pairs == [str(official), str(custom)]           # the missing custom file is skipped, nothing is guessed
    assert "-duc" in argv
