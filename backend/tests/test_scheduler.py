import asyncio
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock

import pytest

from backend.asm.scheduler import ScanScheduler
from backend.jobs.runner import JobRunner
from backend.jobs.scope_resolver import ScopeError
from backend.tests.p2_helpers import environment


def test_tc_sch_1_2_persist_reload_and_disable(settings):
    async def scenario():
        db, _, result = environment(settings)
        runner = JobRunner(settings, db)
        scheduler = ScanScheduler(settings, db, runner)
        row = scheduler.configure(1, "daily", result.config)
        assert row["enabled"] == 1
        assert json.loads(row["config_json"])["depth"] == "light"
        scheduler.start()
        assert scheduler.scheduler.get_job("program-1").next_run_time > datetime.now(timezone.utc)
        await scheduler.close()
        await asyncio.sleep(0)
        restored = ScanScheduler(settings, db, runner)
        restored.start()
        assert len(restored.scheduler.get_jobs()) == 1
        assert restored.scheduler.get_job("program-1").next_run_time.isoformat() == row["next_run_at"]
        restored.configure(1, "daily", result.config, enabled=False)
        assert restored.scheduler.get_jobs() == []
        await restored.close()
        await runner.close()
    asyncio.run(scenario())


def test_scheduled_scan_queues_directly_and_coalesces(settings):
    async def scenario():
        db, _, result = environment(settings)
        runner = JobRunner(settings, db)
        runner.adopt_queued = AsyncMock()
        scheduler = ScanScheduler(settings, db, runner)
        scheduler.configure(1, "6h", result.config)
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        with db.connect() as conn, conn:
            conn.execute("UPDATE schedule SET next_run_at=?", (past,))
        scan_id = await scheduler.dispatch(1)
        runner.adopt_queued.assert_awaited_once_with(scan_id)
        with db.connect() as conn:
            scan = dict(conn.execute("SELECT * FROM scan_run WHERE id=?", (scan_id,)).fetchone())
            assert scan["trigger"] == "scheduled" and scan["status"] == "queued"
            assert json.loads(scan["stats_json"])["resolved_scope"][0]["pattern"] == "example.com"
            assert conn.execute("SELECT depth FROM scan_config WHERE scan_run_id=?", (scan_id,)).fetchone()[0] == "light"
            assert datetime.fromisoformat(conn.execute("SELECT next_run_at FROM schedule").fetchone()[0]) > datetime.now(timezone.utc)
        assert await scheduler.dispatch(1) is None
        with db.connect() as conn, conn:
            conn.execute("UPDATE schedule SET next_run_at=?", (past,))
        assert await scheduler.dispatch(1) is None  # Active scan prevents another.
        runner.adopt_queued.assert_awaited_once()
        await runner.close()
    asyncio.run(scenario())


def test_scheduler_rejects_invalid_interval_and_config(settings):
    db, _, result = environment(settings)
    runner = JobRunner(settings, db)
    scheduler = ScanScheduler(settings, db, runner)
    with pytest.raises(ScopeError):
        scheduler.configure(1, "every_second", result.config)
    with pytest.raises(ScopeError):
        scheduler.configure(1, "daily", result.config.model_copy(update={"scan_timeout": 999999}))
