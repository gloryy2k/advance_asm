"""Wolt Passive #43: data was ingested, the scan stayed "running" for 10+ minutes and Cancel timed out.

Root cause could not be pinned to one step from the evidence, so the guarantees are structural: every step after the
pipeline is announced and bounded, Cancel has its own threads and bounded waits, the final write is retried, and the
per-URL scope decision that made ingest the most expensive step is now per host."""
import asyncio
import json
import threading
import time

import pytest

from backend.jobs.runner import JobRunner
from backend.tests.p2_helpers import FakeEgress, FakeProcess, environment, stop_fake, write_output


def runner_for(settings, db):
    async def factory(command):
        write_output(command.output, "subdomains/all.txt", "example.com\n")
        return FakeProcess()
    return JobRunner(settings, db, process_factory=factory, stopper=stop_fake, egress=FakeEgress())


def test_a_post_step_that_never_returns_cannot_leave_the_scan_running(settings):
    async def scenario():
        db, _, result = environment(settings)
        runner = runner_for(settings, db)
        release = threading.Event()
        runner.diff_engine.apply = lambda *a, **k: release.wait(30)       # blocks "forever" in a worker thread
        runner.POST_LIMITS = {**runner.POST_LIMITS, "diff": 1}
        try:
            await runner.submit(result.scan_id, result.config.model_copy(update={"depth": "light", "scan_timeout": 120}))
            await asyncio.wait_for(runner.queue.join(), 15)
            return runner.status(result.scan_id), runner.logs.replay(result.scan_id)
        finally:
            release.set()
            await runner.close()
    row, events = asyncio.run(scenario())
    assert row["status"] in {"done_partial", "failed"} and row["status"] != "running"
    assert "So sánh với scan trước" in row["error"] and "timeout" in row["error"]
    diff = [e for e in events if e.get("key") == "diff"]
    assert [e["status"] for e in diff] == ["running", "timeout"]            # progress is visible, the step is named
    assert events[-1]["type"] == "done"


def test_every_step_after_the_pipeline_reports_progress_with_timing(settings):
    async def scenario():
        db, _, result = environment(settings)
        runner = runner_for(settings, db)
        try:
            await runner.submit(result.scan_id, result.config.model_copy(update={"depth": "light", "scan_timeout": 120}))
            await asyncio.wait_for(runner.queue.join(), 30)
            return runner.logs.replay(result.scan_id)
        finally:
            await runner.close()
    events = asyncio.run(scenario())
    steps = [(e["key"], e["status"]) for e in events if e.get("type") == "stage" and e.get("key") in {"ingest", "monitors", "diff", "rank", "brief"}]
    assert [k for k, st in steps if st == "ok"][:4] == ["ingest", "monitors", "diff", "rank"]
    assert all("used_s" in e for e in events if e.get("key") == "ingest" and e["status"] == "ok")


def test_cancel_returns_promptly_even_when_every_scan_thread_is_busy(settings):
    async def scenario():
        db, _, result = environment(settings)
        runner = runner_for(settings, db)
        release = threading.Event()
        entered = threading.Event()

        def blocked_ingest(plan):
            entered.set()
            release.wait(60)
            return {}
        runner.ingester.ingest = blocked_ingest
        try:
            await runner.submit(result.scan_id, result.config.model_copy(update={"depth": "light", "scan_timeout": 120}))
            for _ in range(500):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            assert entered.is_set()
            for _ in range(8):                                               # saturate the scan pool: nothing else can start there
                runner.executor.submit(release.wait, 60)
            started = time.monotonic()
            await asyncio.wait_for(runner.cancel(result.scan_id), 15)
            return time.monotonic() - started, runner.status(result.scan_id), runner.logs.replay(result.scan_id)
        finally:
            release.set()
            await runner.close()
    took, row, events = asyncio.run(scenario())
    assert took < 9 and row["status"] == "cancelled"                          # the control threads did the work
    assert events[-1]["type"] == "done" and events[-1]["status"] == "cancelled"


def test_the_final_state_write_is_retried_when_the_database_is_busy(settings, monkeypatch):
    async def scenario():
        db, _, result = environment(settings)
        runner = runner_for(settings, db)
        real, failures = runner._transition, {"n": 0}
        import sqlite3

        def flaky(scan_id, status, error=None, stats=None):
            if status in {"done", "done_partial", "failed"} and failures["n"] < 2:
                failures["n"] += 1
                raise sqlite3.OperationalError("database is locked")
            return real(scan_id, status, error, stats)
        runner._transition = flaky
        monkeypatch.setattr("backend.jobs.runner.asyncio.sleep", lambda s: asyncio.sleep(0))
        try:
            await runner.submit(result.scan_id, result.config.model_copy(update={"depth": "light", "scan_timeout": 120}))
            await asyncio.wait_for(runner.queue.join(), 30)
            return failures["n"], runner.status(result.scan_id)["status"]
        finally:
            await runner.close()
    failures, status = asyncio.run(scenario())
    assert failures == 2 and status in {"done", "done_partial", "failed"}


def test_ingest_decides_scope_once_per_host_not_once_per_url(settings):
    """13k URLs on ~760 hosts used to mean 13k scope decisions and 13k audit writes (minutes on a Docker bind mount)."""
    from backend.jobs.ingest import Ingester
    from backend.jobs.recon_orch import ReconOrchestrator
    db, _, result = environment(settings, ["*.example.com", "example.com", "# OUT", "https://example.com/private"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    command = plan.discoveries[0]
    urls = [f"https://{host}/p{i}" for host in ("a.example.com", "b.example.com", "evil.org") for i in range(300)]
    urls += [f"https://example.com/private/x{i}" for i in range(50)] + [f"https://example.com/ok{i}" for i in range(50)]
    write_output(command.output, "urls/all.txt", "\n".join(urls) + "\n")
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='running' WHERE id=?", (result.scan_id,))
    stats = Ingester(settings, db).ingest(plan)
    funnel = stats["url_funnel"]
    assert funnel["in_scope"] == 650 and funnel["out_of_scope"] == 300 and funnel["path_rule_blocked"] == 50
    audit = [json.loads(line) for line in plan.audit_path.read_text().splitlines()]
    assert len(audit) < 20                                                      # one decision per distinct host, not per URL
    assert {r["host"] for r in audit if r["decision"] == "deny"} >= {"evil.org"}


def test_a_slow_phases_report_is_built_once_and_reused_but_a_fast_one_is_never_stale(settings, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    import backend.asm.phases as phases
    db, _, result = environment(settings)
    calls = {"n": 0}
    real = phases.build_report

    def slow(*args, **kwargs):
        calls["n"] += 1
        time.sleep(0.7)
        return real(*args, **kwargs)
    monkeypatch.setattr(phases, "build_report", slow)
    import backend.api.scans as scans
    scans._REPORT_CACHE.clear()
    with TestClient(create_app(settings)) as client:
        first = client.get(f"/api/scans/{result.scan_id}/phases")
        second = client.get(f"/api/scans/{result.scan_id}/phases")
    assert first.status_code == 200 and second.json() == first.json() and calls["n"] == 1   # reused while the disk is slow
    scans._REPORT_CACHE.clear()
    monkeypatch.setattr(phases, "build_report", real)
    with TestClient(create_app(settings)) as client:
        a = client.get(f"/api/scans/{result.scan_id}/phases").json()
        write_output(settings.BBASM_TARGETS / "example.com" / "recon" / "scans" / str(result.scan_id) / "0", "subdomains/all.txt", "x.example.com\n")
        b = client.get(f"/api/scans/{result.scan_id}/phases").json()
    assert a != b                                                                  # fast reports are rebuilt every time
