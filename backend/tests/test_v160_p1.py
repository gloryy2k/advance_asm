"""arc-bbp Strong #65, P1: nmap in the probe stage (FN1), repo scope limits (F2), and the wrappers that bound nmap/ffuf."""
import json
import stat
import subprocess

import pytest

from backend.jobs.recon_orch import SHIM_DIR, ReconOrchestrator, recon_env
from backend.jobs.runner import JobRunner
from backend.tests.p2_helpers import environment

REPO = "repo:https://github.com/circlefin/malachite"


def strong(settings, db, result, **over):
    JobRunner(settings, db).config(result.scan_id, result.config.model_copy(update={"depth": "strong", "skip_nmap": False, "skip_ffuf": False, "ffuf_confirmed": True, **over}))


def test_probe_stage_never_runs_nmap_but_the_deep_pass_still_may(settings):
    db, _, result = environment(settings, ["*.example.com"])
    strong(settings, db, result)
    config = result.config.model_copy(update={"depth": "strong", "skip_nmap": False})
    assert recon_env(settings, config, settings.BBASM_DATA / "o", probe_only=True)["BBASM_SKIP_NMAP"] == "1"
    assert recon_env(settings, config, settings.BBASM_DATA / "o")["BBASM_SKIP_NMAP"] == "0"          # a deep/explicit-host run on Strong keeps it
    orch = ReconOrchestrator(settings, db)
    plan = orch.build(result.scan_id)
    batches = orch.probe_batches(plan, [f"h{i}.example.com" for i in range(5)])
    assert batches and all(b.env["BBASM_SKIP_NMAP"] == "1" for b in batches)                          # the 126-host probe of #65
    deep_hosts = [b for b in plan.commands if b.stage == "probe"]
    assert deep_hosts and all(c.env["BBASM_SKIP_NMAP"] == "1" for c in deep_hosts)
    out = batches[0].output / "live"
    out.mkdir(parents=True)
    (out / "httpx_full.txt").write_text("https://h1.example.com [200] [Title] [nginx] [1.2.3.4]\n", encoding="utf-8")
    plan.probed_hosts.update(batches[0].hosts)
    deep = orch.deep_command(plan, batches)
    assert deep is not None and deep.stage == "deep" and deep.env["BBASM_SKIP_NMAP"] == "0"


def test_path_restricted_hosts_are_probed_without_nmap_too(settings):
    db, _, result = environment(settings, ["app.example.com"])
    JobRunner(settings, db).config(result.scan_id, result.config.model_copy(update={"depth": "strong", "skip_nmap": False}))
    with db.connect() as conn, conn:
        stats = json.loads(conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (result.scan_id,)).fetchone()[0])
        stats["resolved_scope"].append({"pattern": "https://app.example.com/admin", "kind": "out", "asset_type": "URL", "category": "web", "instruction": ""})
        conn.execute("UPDATE scan_run SET stats_json=? WHERE id=?", (json.dumps(stats), result.scan_id))
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    assert [c.env["BBASM_SKIP_NMAP"] for c in plan.commands] == ["1"]


def restrict(db, scan_id, instruction):
    with db.connect() as conn, conn:
        stats = json.loads(conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (scan_id,)).fetchone()[0])
        for entry in stats["resolved_scope"]:
            if entry["pattern"] == REPO:
                entry["instruction"] = instruction
        conn.execute("UPDATE scan_run SET stats_json=? WHERE id=?", (json.dumps(stats), scan_id))


def test_a_repo_whose_scope_text_limits_it_is_not_scanned_automatically(settings):
    db, _, result = environment(settings, [REPO])
    strong(settings, db, result)
    restrict(db, result.scan_id, "Only code/crates is in scope, except starknet and test")
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    assert plan.commands == []                                                                 # no trufflehog on the whole repo
    assert plan.manual_assets == [{"pattern": REPO, "reason": "restricted_source"}]
    assert any("chưa được quét tự động" in w and "code/crates" in w for w in plan.warnings)
    assert plan.asset_coverage[0]["mode"] == "manual_confirm" and plan.asset_coverage[0]["needs_confirmation"]


def test_the_user_can_confirm_a_whole_repo_scan_and_an_unrestricted_repo_needs_nothing(settings):
    db, _, result = environment(settings, [REPO])
    strong(settings, db, result, source_full_repo_ok=[REPO])
    restrict(db, result.scan_id, "Only code/crates is in scope")
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    assert [c.argv[2:4] for c in plan.commands] == [["--git", "https://github.com/circlefin/malachite"]]
    assert plan.asset_coverage[0]["mode"] == "secrets_only" and "xác nhận" in plan.asset_coverage[0]["detail"]
    db2, _, plain = environment(settings.model_copy(update={"BBASM_DATA": settings.BBASM_DATA / "b", "BBASM_TARGETS": settings.BBASM_TARGETS / "b"}), [REPO])
    strong(settings, db2, plain)
    assert len(ReconOrchestrator(settings, db2).build(plain.scan_id).commands) == 1


def test_mobile_other_and_non_github_repos_are_reported_as_manual(settings):
    db, _, result = environment(settings, ["app:com.acme", "repo:https://gitlab.com/acme/x", "https://app.example.com/login"])
    strong(settings, db, result)
    modes = {c["pattern"]: c["mode"] for c in ReconOrchestrator(settings, db).build(result.scan_id).asset_coverage}
    assert modes["app:com.acme"] == "manual" and modes["repo:https://gitlab.com/acme/x"] == "manual"
    assert modes["https://app.example.com/login"] == "recon_host"


# ── the wrappers ──
FAKE = """#!/bin/bash
printf '%s\\n' "$@" > "$(dirname "$0")/{name}.argv"
{extra}
"""


def run_shim(tmp_path, name, args, extra="", env=None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    real = bin_dir / name
    real.write_text(FAKE.format(name=name, extra=extra))
    real.chmod(real.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    full = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path), "RECON_OUT_DIR": str(out), **(env or {})}
    return subprocess.run([str(SHIM_DIR / name), *args], env=full, timeout=30, capture_output=True), bin_dir, out


def test_nmap_wrapper_caps_each_host_and_the_whole_run(tmp_path):
    result, bin_dir, _ = run_shim(tmp_path, "nmap", ["-sV", "--top-ports", "1000"], env={"BBASM_NMAP_HOST_TIMEOUT": "90", "BBASM_NMAP_TIMEOUT": "60"})
    assert result.returncode == 0
    argv = (bin_dir / "nmap.argv").read_text().split()
    assert argv[:4] == ["--max-retries", "1", "--host-timeout", "90s"] and argv[4:] == ["-sV", "--top-ports", "1000"]
    run_shim(tmp_path, "nmap", ["--host-timeout", "5s", "--max-retries", "3", "x"])
    argv = (bin_dir / "nmap.argv").read_text().split()
    assert argv.count("--host-timeout") == 1 and "5s" in argv and argv.count("--max-retries") == 1               # a choice is not overridden


def test_nmap_wrapper_says_when_it_stopped_a_run(tmp_path):
    from backend.jobs.recon_orch import read_tool_notes
    result, _, out = run_shim(tmp_path, "nmap", ["x"], extra="sleep 20", env={"BBASM_NMAP_TIMEOUT": "1"})
    assert result.returncode == 0                                                                    # the scan carries on with what nmap wrote
    note = read_tool_notes(out)[0]
    assert note["tool"] == "nmap" and "DỞ DANG" in note["note"]


def test_ffuf_wrapper_calibrates_and_bounds_the_run(tmp_path):
    from backend.jobs.recon_orch import read_tool_notes
    _, bin_dir, out = run_shim(tmp_path, "ffuf", ["-u", "https://a.example.com/FUZZ", "-mc", "200,403"], env={"BBASM_FFUF_MAXTIME": "120"})
    argv = (bin_dir / "ffuf.argv").read_text().split()
    assert argv[:3] == ["-maxtime", "120", "-ac"] and "-mc" in argv
    assert "hiệu chuẩn" in read_tool_notes(out)[0]["note"]
    run_shim(tmp_path, "ffuf", ["-fs", "4547", "-u", "x"], env={"BBASM_FFUF_MAXTIME": "0"})
    argv = (bin_dir / "ffuf.argv").read_text().split()
    assert "-ac" not in argv and "-maxtime" not in argv and "-fs" in argv                            # the user's own filter wins


def test_ffuf_log_line_tells_apart_missing_binary_no_live_host_and_config(settings, tmp_path, monkeypatch):
    """arc-bbp #65 logged "ffuf not installed or no live hosts" in a stage where ffuf was installed and simply had no host yet."""
    from backend.log_buffer import ReconLogParser
    line = "[!] ffuf not installed or no live hosts — skipping directory fuzzing"
    base = {"depth": "strong", "skip_ffuf": False}
    cfg = lambda **o: type("C", (), {**base, **o})()
    settings.BBASM_BBROOT = __import__("backend.config", fromlist=["PROJECT_ROOT"]).PROJECT_ROOT / "vendor/claude-bug-bounty"
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(type(settings), "tool_search_path", lambda self: str(empty))
    assert ReconLogParser(settings, cfg()).classify(line)[0] == "missing_tool"
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "ffuf").write_text("#!/bin/sh\n")
    (fake / "ffuf").chmod(0o755)
    monkeypatch.setattr(type(settings), "tool_search_path", lambda self: str(fake))
    tag, message = ReconLogParser(settings, cfg()).classify(line)
    assert tag == "no_input" and "chưa có host đang sống" in message
    assert ReconLogParser(settings, cfg(depth="light")).classify(line)[0] == "skipped_config"
    assert ReconLogParser(settings, cfg(skip_ffuf=True)).classify(line)[0] == "skipped_config"


# ── F7: *.arc.io does not include arc.io; adding it is an explicit, confirmed, previewed choice ──
def apex_scan(settings, **over):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.tests.test_v152_lifecycle import settings_for
    client = TestClient(create_app(settings_for(settings)))
    client.__enter__()
    made = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["*.arc.io"], "scope_out": ["https://arc.io/admin"], "name": "arc"}).json()
    return client, made["scan_id"], client.get(f"/api/scans/{made['scan_id']}/config").json() | over


def test_the_apex_is_outside_a_wildcard_unless_the_user_adds_it_with_confirmation(settings):
    client, scan, cfg = apex_scan(settings)
    try:
        info = client.post(f"/api/scans/{scan}/coverage", json=cfg).json()
        assert info["apex"] == [{"apex": "arc.io", "wildcard": "*.arc.io", "status": "not_in_scope", "dropped_urls": 0, "selected": False, "confirmed": False}]
        assert info["assets"][0]["mode"] == "recon" and "domain gốc không được cấp quyền" in info["assets"][0]["detail"]
        assert [s["key"] for s in info["stage_shares"]] == ["discovery", "main", "probe", "deep"]
        chosen = {**cfg, "include_apex": ["arc.io"], "apex_confirmed": True}
        assert client.post(f"/api/scans/{scan}/coverage", json=chosen).json()["apex"][0]["status"] == "added_by_you"
        # the plan really contains the apex, and an OUT rule on a path of it is still enforced
        from backend.jobs.recon_orch import ReconOrchestrator
        from backend.jobs.runner import JobRunner
        from backend.models import ScanConfig
        JobRunner(client.app.state.settings, client.app.state.database).config(scan, ScanConfig.model_validate({**chosen, "depth": "light"}))
        plan = ReconOrchestrator(client.app.state.settings, client.app.state.database).build(scan)
        assert plan.gate.in_scope("https://arc.io/") and not plan.gate.in_scope("https://arc.io/admin/x") and plan.gate.in_scope("https://api.arc.io/")
        assert "arc.io" in plan.explicit_hosts and any("Domain gốc arc.io được thêm" in w for w in plan.warnings)
        # listed but NOT confirmed: nothing is added
        second = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["*.arc.io"], "scope_out": ["https://arc.io/admin"], "name": "arc"}).json()["scan_id"]
        unconfirmed = ScanConfig.model_validate({**cfg, "include_apex": ["arc.io"], "apex_confirmed": False, "depth": "light"})
        JobRunner(client.app.state.settings, client.app.state.database).config(second, unconfirmed)
        plan = ReconOrchestrator(client.app.state.settings, client.app.state.database).build(second)
        assert not plan.gate.in_scope("https://arc.io/") and "arc.io" not in plan.explicit_hosts
    finally:
        client.__exit__(None, None, None)


def test_launch_refuses_an_unconfirmed_apex_and_an_apex_that_is_not_a_wildcard_apex_is_ignored(settings):
    client, scan, cfg = apex_scan(settings)
    try:
        from backend.api.scans import require_apex
        from backend.jobs.scope_resolver import ScopeError
        from backend.models import ScanConfig
        import pytest
        with pytest.raises(ScopeError) as err:
            require_apex(ScanConfig.model_validate({**cfg, "include_apex": ["arc.io"]}))
        assert err.value.code == "apex_confirm_required"
        from backend.scope_selection import included_apex
        stray = ScanConfig.model_validate({**cfg, "include_apex": ["evil.com", "arc.io"], "apex_confirmed": True})
        assert included_apex(client.get(f"/api/scans/{scan}/review").json()["scope"], stray) == ["arc.io"]       # only the apex of an IN wildcard
        assert client.put(f"/api/scans/{scan}/config", json={**cfg, "include_apex": ["not a domain"]}).status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_coverage_lists_how_each_tool_holds_an_out_path_rule(settings):
    client, scan, cfg = apex_scan(settings)
    try:
        info = client.post(f"/api/scans/{scan}/coverage", json=cfg).json()
        assert info["path_rules"]["hosts"] == {"arc.io": ["/admin"]} or "arc.io" in info["path_rules"]["hosts"]
        tools = {t["tool"]: t for t in info["path_rules"]["enforcement"]}
        assert tools["katana / nuclei / ffuf / nmap"]["stops_request"] is True                  # locked to probe-only
        loose = client.post(f"/api/scans/{scan}/coverage", json={**cfg, "allow_active_on_path_rules": True}).json()
        assert {t["tool"]: t for t in loose["path_rules"]["enforcement"]}["katana / nuclei / ffuf / nmap"]["stops_request"] is False
    finally:
        client.__exit__(None, None, None)
