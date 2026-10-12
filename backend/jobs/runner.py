"""Bounded asyncio job queue; subprocess groups, cancellation and partial output."""

import asyncio
import codecs
import json
import os
import signal

from backend.db import utc_now
from backend.jobs.recon_orch import ClosedEgress, ReconOrchestrator, read_config
from backend.jobs.scope_resolver import ScopeError
from backend.log_buffer import LogBuffer, ReconLogParser
from backend.scope_gate import audit, normalize_pattern


def store_config(conn, scan_id, config):
    conn.execute("UPDATE scan_config SET depth=?,threads=?,rate_limit=?,scan_timeout=?,nuclei_severity=?,skip_nmap=?,skip_nuclei=?,skip_active_crawl=?,categories_enabled_json=?,excluded_hosts_json=? WHERE scan_run_id=?", (
        config.depth, config.threads, config.rate_limit, config.scan_timeout, config.nuclei_severity,
        config.skip_nmap, config.skip_nuclei, config.skip_active_crawl,
        json.dumps(config.categories_enabled), json.dumps(config.excluded_hosts), scan_id))
    conn.execute("UPDATE scan_run SET depth=? WHERE id=?", (config.depth, scan_id))


async def spawn_process(command):
    if os.name != "posix":
        raise RuntimeError("Real recon requires Linux/WSL2/container process groups")
    return await asyncio.create_subprocess_exec(
        *command.argv, env=command.env, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT, start_new_session=True,
    )


async def stop_process_group(process, grace=1.0):
    # pid is the session/process-group ID from start_new_session=True. Use it even
    # after the parent exits so surviving grandchildren are not left behind.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), grace)
    except asyncio.TimeoutError:
        pass
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    await process.wait()


class JobRunner:
    def __init__(self, settings, database, *, process_factory=spawn_process, stopper=stop_process_group,
                 egress=None, orchestrator=None, ingester=None):
        self.settings, self.database = settings, database
        self.process_factory, self.stopper = process_factory, stopper
        self.egress = egress or ClosedEgress()
        self.orchestrator = orchestrator or ReconOrchestrator(settings, database)
        if ingester is None:
            from backend.jobs.ingest import Ingester
            ingester = Ingester(settings, database)
        self.ingester = ingester
        self.logs = LogBuffer(settings.BBASM_DATA / "logs")
        self.queue, self.workers, self.tasks = asyncio.Queue(), [], {}
        self.submitted, self.program_locks = set(), {}
        self.closing = False

    def recover(self):
        """Never silently relaunch a scan after an interrupted dashboard process."""
        if not self.database.path.exists():
            return
        with self.database.connect() as conn, conn:
            conn.execute("UPDATE scan_run SET status='failed',finished_at=?,error='Dashboard interrupted; create a new scan to retry' WHERE status IN ('queued','running')", (utc_now(),))

    def config(self, scan_id, new_config=None):
        if not self.database.path.exists():
            raise ScopeError("Scan not found", "scan_not_found")
        with self.database.connect() as conn, conn:
            if new_config is not None:
                conn.execute("BEGIN IMMEDIATE")
            scan = conn.execute("SELECT * FROM scan_run WHERE id=?", (scan_id,)).fetchone()
            if scan is None:
                raise ScopeError("Scan not found", "scan_not_found")
            if new_config is not None:
                if scan["status"] != "draft":
                    raise ScopeError("Only draft config can be edited", "invalid_state")
                self._validate(new_config)
                store_config(conn, scan_id, new_config)
            return read_config(conn.execute("SELECT * FROM scan_config WHERE scan_run_id=?", (scan_id,)).fetchone())

    def _validate(self, config):
        if config.scan_timeout > self.settings.scan_timeout(config.depth):
            raise ScopeError("scan_timeout exceeds configured depth hard limit")
        for pattern in config.excluded_hosts:
            try:
                normalize_pattern(pattern)
            except ValueError:
                raise ScopeError("Invalid excluded scope pattern") from None

    def _enqueue(self, scan_id, config):
        if not self.database.path.exists():
            raise ScopeError("Scan not found", "scan_not_found")
        with self.database.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status FROM scan_run WHERE id=?", (scan_id,)).fetchone()
            if row is None or row["status"] != "draft":
                raise ScopeError("Only draft scans can be launched", "invalid_state")
            config = config or read_config(conn.execute("SELECT * FROM scan_config WHERE scan_run_id=?", (scan_id,)).fetchone())
            self._validate(config)
            store_config(conn, scan_id, config)
            conn.execute("UPDATE scan_run SET status='queued' WHERE id=?", (scan_id,))

    async def submit(self, scan_id, config=None):
        if self.closing:
            raise ScopeError("Runner is shutting down")
        await asyncio.to_thread(self._enqueue, scan_id, config)
        self.submitted.add(scan_id)
        await self.logs.emit(scan_id, "log", message="Scan queued")
        self.queue.put_nowait(scan_id)
        if not self.workers:
            self.workers = [asyncio.create_task(self._worker()) for _ in range(self.settings.BBASM_MAX_CONCURRENT_SCANS)]

    def status(self, scan_id):
        if not self.database.path.exists():
            raise ScopeError("Scan not found", "scan_not_found")
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM scan_run WHERE id=?", (scan_id,)).fetchone()
        if row is None:
            raise ScopeError("Scan not found", "scan_not_found")
        return dict(row)

    def _transition(self, scan_id, status, error=None, stats=None):
        with self.database.connect() as conn, conn:
            current = conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (scan_id,)).fetchone()
            merged = json.loads(current[0] or "{}")
            merged.update(stats or {})
            if status == "running":
                return conn.execute("UPDATE scan_run SET status='running',started_at=? WHERE id=? AND status='queued'", (utc_now(), scan_id)).rowcount
            conn.execute("UPDATE scan_run SET status=?,finished_at=?,error=?,stats_json=? WHERE id=?", (
                status, utc_now(), error, json.dumps(merged), scan_id))

    async def _worker(self):
        while True:
            scan_id = await self.queue.get()
            try:
                if scan_id not in self.submitted:
                    continue
                task = asyncio.create_task(self._execute(scan_id))
                self.tasks[scan_id] = task
                await task
            except asyncio.CancelledError:
                if self.closing:
                    return
            except Exception as exc:
                # An audit/log I/O error must not silently remove a queue worker.
                await asyncio.to_thread(self._transition, scan_id, "failed", f"Worker error: {type(exc).__name__}")
            finally:
                self.tasks.pop(scan_id, None)
                self.submitted.discard(scan_id)
                self.queue.task_done()

    async def _execute(self, scan_id):
        plan, stats, errors, cancelled = None, {}, [], False
        try:
            row = await asyncio.to_thread(self.status, scan_id)
            lock = self.program_locks.setdefault(row["program_id"], asyncio.Lock())
            async with lock:
                if not await asyncio.to_thread(self._transition, scan_id, "running"):
                    return
                plan = await asyncio.to_thread(self.orchestrator.build, scan_id)
                for message in plan.warnings:
                    await self.logs.emit(scan_id, "log", level="warning", message=message)
                for name in self.orchestrator.missing_tools():
                    await self.logs.emit(scan_id, "log", level="warning", message=f"{name} missing; framework will skip unavailable tools")
                parser = ReconLogParser(self.settings)
                try:
                    await asyncio.wait_for(self._pipeline(plan, parser, errors),
                        min(plan.config.scan_timeout, self.settings.scan_timeout(plan.config.depth)))
                except asyncio.TimeoutError:
                    errors.append("Scan hard timeout exceeded")
                # _pipeline guarantees process cleanup before we inspect partial files.
                stats = await asyncio.to_thread(self.ingester.ingest, plan)
        except asyncio.CancelledError:
            cancelled = True
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        if cancelled:
            status = "cancelled"
        elif errors:
            status = "done_partial" if stats.get("observed", 0) else "failed"
        else:
            status = "done"
        await asyncio.to_thread(self._transition, scan_id, status, "; ".join(errors)[:2000] or None, stats)
        if plan:
            audit(plan.audit_path, plan.slug, status, "scan_finished", scan_id=scan_id)
        await self.logs.emit(scan_id, "done", status=status, stats=stats, error="; ".join(errors)[:2000] or None)

    async def _pipeline(self, plan, parser, errors):
        initial = list(plan.commands)
        if not initial and not plan.warnings:
            errors.append("No eligible recon commands")
        for command in initial:
            await self._command(plan, command, parser, errors)
        for command in self.orchestrator.discovered_commands(plan):
            await self._command(plan, command, parser, errors)

    async def _command(self, plan, command, parser, errors):
        process = None
        try:
            self.egress.check(plan, command)
            process = await self.process_factory(command)
            decoder, pending = codecs.getincrementaldecoder("utf-8")("replace"), ""
            while chunk := await process.stdout.read(4096):
                pending += decoder.decode(chunk)
                while "\n" in pending or len(pending) > 4096:
                    if "\n" in pending:
                        line, pending = pending.split("\n", 1)
                    else:
                        line, pending = pending[:4096], pending[4096:]
                    kind, payload = parser.parse(line)
                    await self.logs.emit(plan.scan_id, kind, **payload)
            pending += decoder.decode(b"", final=True)
            if pending:
                kind, payload = parser.parse(pending)
                await self.logs.emit(plan.scan_id, kind, **payload)
            code = await process.wait()
            if code != 0:
                errors.append(f"{command.category} subprocess exited {code}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            if process is not None:
                # Shield teardown so cancellation cannot leave grandchildren running.
                await asyncio.shield(self.stopper(process))

    async def cancel(self, scan_id):
        row = await asyncio.to_thread(self.status, scan_id)
        if row["status"] in {"done", "done_partial", "failed", "cancelled"}:
            return
        task = self.tasks.get(scan_id)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            # A Task cancelled before its coroutine starts never enters _execute's
            # exception handler. Persist cancellation in that race as well.
            if (await asyncio.to_thread(self.status, scan_id))["status"] in {"queued", "running"}:
                await asyncio.to_thread(self._transition, scan_id, "cancelled")
                await self.logs.emit(scan_id, "done", status="cancelled")
        else:
            self.submitted.discard(scan_id)
            await asyncio.to_thread(self._transition, scan_id, "cancelled")
            await self.logs.emit(scan_id, "done", status="cancelled")

    async def close(self):
        self.closing = True
        for scan_id in list(self.submitted):
            await self.cancel(scan_id)
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
