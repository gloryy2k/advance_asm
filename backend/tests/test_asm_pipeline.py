import asyncio
from datetime import datetime, timedelta, timezone
import json
import pytest

from backend.asm.scheduler import ScanScheduler
from backend.jobs.runner import JobRunner
from backend.jobs.scope_resolver import ScopeError
from backend.tests.p2_helpers import FakeProcess, environment, stop_fake, write_output


def test_runner_monitors_diff_rank_and_scheduled_rescan(settings, monkeypatch):
    async def scenario():
        db, _, result = environment(settings)
        calls = []

        async def factory(command):
            calls.append(command.category)
            if command.category == "web":
                write_output(command.output, "subdomains/all.txt", "example.com\n")
                write_output(command.output, "live/httpx_full.txt", "https://example.com [200] [API login] [GraphQL]\n")
                write_output(command.output, "urls/js_files.txt", "https://example.com/app.js\n")
                write_output(command.output, "js/endpoints.txt", "https://example.com/api\n")
                write_output(command.output, "nuclei/findings.jsonl", json.dumps({
                    "template-id": "test", "matched-at": "https://example.com", "info": {"severity": "medium"}}) + "\n")
            elif command.category == "takeover":
                write_output(command.output, "dnsreaper.json", '[{"domain":"example.com","service":"s3"}]')
            elif command.category == "secret":
                write_output(command.output, "trufflehog.jsonl", '{"DetectorName":"AWS","Verified":false}\n')
            return FakeProcess()

        runner = JobRunner(settings, db, process_factory=factory, stopper=stop_fake)
        monkeypatch.setattr(runner.monitors, "available", lambda *tools: True)
        try:
            await runner.submit(result.scan_id)
            await runner.queue.join()
            assert calls == ["web", "takeover", "secret"]
            status = runner.status(result.scan_id)
            assert status["status"] == "done"
            stats = json.loads(status["stats_json"])
            assert stats["findings"] == 4
            assert stats["diff"] == {"new": 1, "changed": 0, "gone": 0}
            with db.connect() as conn:
                assert conn.execute("SELECT rank_score FROM asset").fetchone()[0] == 10
            records = [json.loads(line) for p in settings.BBASM_TARGETS.rglob("audit.jsonl") for line in p.read_text().splitlines()]
            assert len([r for r in records if r["rule"] == "audited_spawn"]) == 3
            scheduler = ScanScheduler(settings, db, runner)
            scheduler.configure(status["program_id"], "daily", result.config)
            with db.connect() as conn, conn:
                conn.execute("UPDATE schedule SET next_run_at=?", ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),))
            second = await scheduler.dispatch(status["program_id"])
            await runner.queue.join()
            status = runner.status(second)
            assert status["status"] == "done" and status["trigger"] == "scheduled"
            assert json.loads(status["stats_json"])["diff"] == {"new": 0, "changed": 0, "gone": 0}
            with db.connect() as conn:
                assert conn.execute("SELECT count(*) FROM finding").fetchone()[0] == 4
        finally:
            await runner.close()
    asyncio.run(scenario())


def test_scheduled_queue_guards_and_long_monitor_logs(settings):
    async def scenario():
        db, _, result = environment(settings)
        runner = JobRunner(settings, db, stopper=stop_fake)
        with pytest.raises(ScopeError):
            await runner.adopt_queued(result.scan_id)  # Draft is not a scheduled queue entry.
        with pytest.raises(ScopeError):
            runner.status(999999)
        with pytest.raises(ScopeError):
            runner.config(999999, result.config)
        with pytest.raises(ScopeError):
            runner.config(result.scan_id, result.config.model_copy(update={"excluded_hosts": ["bad host"]}))

        async def factory(command):
            process = FakeProcess()
            process.stdout = asyncio.StreamReader()
            process.stdout.feed_data(b"x" * 9000 + b"\nlast line without newline")
            process.stdout.feed_eof()
            return process

        runner.process_factory = factory
        await runner.submit(result.scan_id)
        await runner.adopt_queued(result.scan_id)  # Already submitted: no duplicate.
        await runner.queue.join()
        assert runner.status(result.scan_id)["status"] == "done"
        await runner.cancel(result.scan_id)  # Terminal scan stays done.
        assert any(e.get("message") == "last line without newline" for e in runner.logs.replay(result.scan_id))
        await runner.close()
        with pytest.raises(ScopeError):
            await runner.submit(result.scan_id)
        with pytest.raises(ScopeError):
            await runner.adopt_queued(result.scan_id)
    asyncio.run(scenario())
