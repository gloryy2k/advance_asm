import asyncio
import json
import signal
from unittest.mock import AsyncMock, Mock

import pytest

from backend.jobs.runner import JobRunner, stop_process_group
from backend.models import ResolveRequest
from backend.tests.p2_helpers import FakeEgress, FakeProcess, environment, stop_fake, until, write_output


def test_tc_run_1_queue_limits_concurrency(settings):
    async def scenario():
        db, resolver, first = environment(settings)
        results = [first] + [resolver.resolve(ResolveRequest(input="raw", scope=[f"target{i}.example.com"])) for i in range(2)]
        processes = []

        async def factory(command):
            process = FakeProcess(hold=True)
            processes.append(process)
            return process

        runner = JobRunner(settings, db, process_factory=factory, stopper=stop_fake, egress=FakeEgress())
        try:
            for result in results:
                await runner.submit(result.scan_id)
            await until(lambda: len(processes) == 2)
            assert runner.status(results[2].scan_id)["status"] == "queued"
            await stop_fake(processes[0])
            await until(lambda: len(processes) == 3)
            await stop_fake(processes[1])
            await stop_fake(processes[2])
            await runner.queue.join()
            assert all(runner.status(item.scan_id)["status"] == "done" for item in results)
        finally:
            await runner.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("output,expected", [(True, "done_partial"), (False, "failed")])
def test_tc_run_4_nonzero_exit_ingests_partial(settings, output, expected):
    async def scenario():
        db, _, result = environment(settings)

        async def factory(command):
            if output:
                write_output(command.output, "subdomains/all.txt", "example.com\n")
            return FakeProcess(code=2)

        runner = JobRunner(settings, db, process_factory=factory, stopper=stop_fake, egress=FakeEgress())
        try:
            await runner.submit(result.scan_id)
            await runner.queue.join()
            row = runner.status(result.scan_id)
            assert row["status"] == expected
            assert "exited 2" in row["error"]
            assert "resolved_scope" in json.loads(row["stats_json"])
            assert any(item["type"] == "phase" for item in runner.logs.replay(result.scan_id))
            assert runner.logs.replay(result.scan_id)[-1]["type"] == "done"
        finally:
            await runner.close()
    asyncio.run(scenario())


def test_tc_run_2_cancel_running_and_queued(settings):
    async def scenario():
        settings.BBASM_MAX_CONCURRENT_SCANS = 1
        db, resolver, result = environment(settings)
        other = resolver.resolve(ResolveRequest(input="raw", scope=["other.example.com"]))
        processes = []

        async def factory(command):
            process = FakeProcess(hold=True)
            processes.append(process)
            return process

        runner = JobRunner(settings, db, process_factory=factory, stopper=stop_fake, egress=FakeEgress())
        try:
            await runner.submit(result.scan_id)
            await runner.submit(other.scan_id)
            await until(lambda: len(processes) == 1)
            await runner.cancel(other.scan_id)
            await runner.cancel(result.scan_id)
            await runner.queue.join()
            assert processes[0].killed
            assert len(processes) == 1
            assert runner.status(result.scan_id)["status"] == "cancelled"
            assert runner.status(other.scan_id)["status"] == "cancelled"
        finally:
            await runner.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("output,expected", [(True, "done_partial"), (False, "failed")])
def test_tc_run_3_hard_timeout(settings, output, expected):
    async def scenario():
        settings.BBASM_SCAN_TIMEOUT_LIGHT = 1
        db, _, result = environment(settings)
        processes = []

        async def factory(command):
            if output:
                write_output(command.output, "subdomains/all.txt", "example.com\n")
            process = FakeProcess(hold=True)
            processes.append(process)
            return process

        runner = JobRunner(settings, db, process_factory=factory, stopper=stop_fake, egress=FakeEgress())
        try:
            await runner.submit(result.scan_id)
            await runner.queue.join()
            assert runner.status(result.scan_id)["status"] == expected
            assert processes[0].killed
            assert "timeout" in runner.status(result.scan_id)["error"]
        finally:
            await runner.close()
    asyncio.run(scenario())


def test_process_tree_term_then_kill_includes_new_session_members(monkeypatch):
    async def scenario():
        from types import SimpleNamespace
        children = [Mock(pid=pid) for pid in (12345, 12346, 12347)]
        snapshots = Mock(side_effect=[{p.pid: p for p in children[:2]}, {children[2].pid: children[2]}])
        monkeypatch.setattr("backend.jobs.runner.process_family", snapshots)
        wait = Mock(return_value=([], children[1:2]))
        monkeypatch.setattr("backend.jobs.runner.psutil.wait_procs", wait)
        killpg = Mock()
        monkeypatch.setattr("backend.jobs.runner.os", SimpleNamespace(name="posix", killpg=killpg))
        monkeypatch.setattr("backend.jobs.runner.signal.SIGKILL", 9, raising=False)
        process = FakeProcess()
        await stop_process_group(process, grace=0.1)
        for child in children[:2]:
            child.terminate.assert_called_once()
        for child in children:
            child.kill.assert_called_once()
        wait.assert_called_once_with(children[1:2], timeout=0.1)
        killpg.assert_called_once_with(12345, 9)
    asyncio.run(scenario())


def test_process_family_finds_orphans_after_root_exits(monkeypatch):
    import psutil
    from types import SimpleNamespace
    from backend.jobs.runner import process_family
    monkeypatch.setattr("backend.jobs.runner.psutil.Process", Mock(side_effect=psutil.NoSuchProcess(12345)))
    orphan, unrelated = Mock(pid=12346), Mock(pid=98765)
    monkeypatch.setattr("backend.jobs.runner.psutil.process_iter", lambda: [orphan, unrelated])
    monkeypatch.setattr("backend.jobs.runner.os", SimpleNamespace(name="posix", getsid=lambda pid: 12345 if pid == 12346 else 98765))
    assert process_family(12345) == {12346: orphan}


def test_process_family_includes_detached_descendants(monkeypatch):
    from types import SimpleNamespace
    from backend.jobs.runner import process_family
    root, child, grandchild = Mock(pid=1), Mock(pid=2), Mock(pid=3)
    root.children.return_value = [child, grandchild]
    monkeypatch.setattr("backend.jobs.runner.psutil.Process", lambda pid: root)
    monkeypatch.setattr("backend.jobs.runner.os", SimpleNamespace(name="nt"))
    assert process_family(1) == {1: root, 2: child, 3: grandchild}
    root.children.assert_called_once_with(recursive=True)


def test_disabled_runner_refuses_live_egress_without_spawning(settings):
    settings.BBASM_RECON_DISABLED = True
    async def scenario():
        db, _, result = environment(settings)
        factory = AsyncMock()
        runner = JobRunner(settings, db, process_factory=factory)
        try:
            await runner.submit(result.scan_id)
            await runner.queue.join()
            factory.assert_not_called()
            row = runner.status(result.scan_id)
            assert row["status"] == "failed"
            assert "Live recon disabled" in row["error"]
        finally:
            await runner.close()
    asyncio.run(scenario())


def test_default_runner_audits_before_spawn_and_completes(settings):
    async def scenario():
        db, _, result = environment(settings)
        observed = []

        async def factory(command):
            records = [json.loads(line) for path in settings.BBASM_TARGETS.rglob("audit.jsonl")
                       for line in path.read_text().splitlines()]
            assert any(r["rule"] == "audited_spawn" and r["decision"] == "allow"
                       and r["scan_id"] == result.scan_id and r["resource"] == command.resource for r in records)
            observed.append(runner.status(result.scan_id)["status"])
            return FakeProcess()

        runner = JobRunner(settings, db, process_factory=factory, stopper=stop_fake)
        try:
            await runner.submit(result.scan_id)
            await runner.queue.join()
            assert observed == ["running"]
            assert runner.status(result.scan_id)["status"] == "done"
        finally:
            await runner.close()
    asyncio.run(scenario())


def test_restart_never_silently_relaunches_interrupted_jobs(settings):
    db, _, result = environment(settings)
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='running' WHERE id=?", (result.scan_id,))
    factory = AsyncMock()
    runner = JobRunner(settings, db, process_factory=factory)
    runner.recover()
    assert runner.status(result.scan_id)["status"] == "failed"
    assert "interrupted" in runner.status(result.scan_id)["error"]
    factory.assert_not_called()


def test_native_spawn_creates_session_and_never_uses_shell(monkeypatch):
    from types import SimpleNamespace
    from backend.jobs.runner import spawn_process
    async def scenario():
        spawn = AsyncMock(return_value="process")
        monkeypatch.setattr("backend.jobs.runner.os", SimpleNamespace(name="posix"))
        monkeypatch.setattr("backend.jobs.runner.asyncio.create_subprocess_exec", spawn)
        command = SimpleNamespace(argv=["bash", "engine.sh", "target-list.txt"], env={"BB_THREADS": "12"})
        assert await spawn_process(command) == "process"
        assert spawn.call_args.args == tuple(command.argv)
        assert spawn.call_args.kwargs["start_new_session"] is True
        assert "shell" not in spawn.call_args.kwargs
    asyncio.run(scenario())
