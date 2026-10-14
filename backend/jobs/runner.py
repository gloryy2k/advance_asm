"""Bounded asyncio job queue; subprocess groups, cancellation and partial output."""

import asyncio
import codecs
from datetime import datetime, timedelta, timezone
import json
import os
import signal
import sys
import psutil

from backend.db import utc_now
from backend.jobs.recon_orch import AuditedEgress, ClosedEgress, ReconOrchestrator, read_config
from backend.jobs.scope_resolver import ScopeError
from backend.log_buffer import LogBuffer, ReconLogParser
from backend.scope_gate import audit, normalize_pattern
from backend.trust import launch_gate, scope_trust


def store_config(conn, scan_id, config):
    conn.execute("UPDATE scan_config SET depth=?,threads=?,rate_limit=?,scan_timeout=?,nuclei_severity=?,skip_nmap=?,skip_nuclei=?,skip_active_crawl=?,categories_enabled_json=?,excluded_hosts_json=?,options_json=? WHERE scan_run_id=?", (
        config.depth, config.threads, config.rate_limit, config.scan_timeout, config.nuclei_severity,
        config.skip_nmap, config.skip_nuclei, config.skip_active_crawl,
        json.dumps(config.categories_enabled), json.dumps(config.excluded_hosts), json.dumps(config.options()), scan_id))
    conn.execute("UPDATE scan_run SET depth=? WHERE id=?", (config.depth, scan_id))


async def spawn_process(command):
    if os.name != "posix":
        raise RuntimeError("Real recon requires Linux/WSL2/container process groups")
    return await asyncio.create_subprocess_exec(
        *command.argv, env=command.env, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT, start_new_session=True,
    )


def process_family(pid):
    """Include orphaned session members as well as children in separate groups."""
    members = {}
    try:
        root = psutil.Process(pid)
        members = {p.pid: p for p in root.children(recursive=True)}
        members[pid] = root
    except psutil.NoSuchProcess:
        pass
    if os.name == "posix":
        for candidate in psutil.process_iter():
            try:
                if os.getsid(candidate.pid) == pid:
                    members[candidate.pid] = candidate
            except (ProcessLookupError, psutil.NoSuchProcess):
                continue
    return members


def terminate_family(pid, grace):
    members = process_family(pid)
    for child in members.values():
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    # asyncio owns waitpid for the root; psutil must not reap it.
    psutil.wait_procs([p for p in members.values() if p.pid != pid], timeout=grace)
    # Re-snapshot the session: bash may have exited/reparented its descendants,
    # or a child may have spawned between the first snapshot and SIGTERM.
    for child_pid, child in process_family(pid).items():
        members.setdefault(child_pid, child)
    for child in members.values():
        try:
            child.kill()  # psutil checks process identity against PID reuse.
        except psutil.NoSuchProcess:
            pass
    if os.name == "posix":
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


async def stop_process_group(process, grace=1.0):
    await asyncio.to_thread(terminate_family, process.pid, grace)
    await process.wait()


class JobRunner:
    def __init__(self, settings, database, *, process_factory=spawn_process, stopper=stop_process_group,
                 egress=None, orchestrator=None, ingester=None):
        self.settings, self.database = settings, database
        self.process_factory, self.stopper = process_factory, stopper
        self.egress = egress if egress is not None else (ClosedEgress() if settings.BBASM_RECON_DISABLED else AuditedEgress())
        self.orchestrator = orchestrator or ReconOrchestrator(settings, database)
        if ingester is None:
            from backend.jobs.ingest import Ingester
            ingester = Ingester(settings, database)
        self.ingester = ingester
        from backend.asm.diff_engine import DiffEngine
        from backend.asm.monitors import Monitors
        self.diff_engine = DiffEngine(database)
        self.monitors = Monitors(settings, database)
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
        self.purge_drafts()

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

    def _enqueue(self, scan_id, config, ack=False):
        if os.name != "posix" and self.process_factory is spawn_process and not self.settings.BBASM_RECON_DISABLED:
            raise ScopeError("Máy chủ chạy trên Windows gốc nên không chạy được recon. Dùng Docker hoặc WSL2.", "platform_unsupported")
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
            self._apply_scope_snapshot(conn, scan_id)
            if ack:  # same transaction as queueing: a fast worker can never run before the confirmation is stored
                stats = json.loads(conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (scan_id,)).fetchone()["stats_json"] or "{}")
                stats["automation_ack"] = utc_now()
                conn.execute("UPDATE scan_run SET stats_json=? WHERE id=?", (json.dumps(stats), scan_id))
            conn.execute("UPDATE scan_run SET status='queued' WHERE id=?", (scan_id,))
        if ack:
            self._audit_ack(scan_id)

    @staticmethod
    def _apply_scope_snapshot(conn, scan_id):
        """Launch is the moment the reviewed scope becomes the program's scope (schedules read it)."""
        row = conn.execute("SELECT program_id,stats_json FROM scan_run WHERE id=?", (scan_id,)).fetchone()
        entries = json.loads(row["stats_json"] or "{}").get("resolved_scope") or []
        if not entries:
            return
        conn.execute("DELETE FROM scope_rule WHERE program_id=?", (row["program_id"],))
        conn.executemany("INSERT INTO scope_rule(program_id,pattern,kind,asset_type) VALUES(?,?,?,?)",
                         [(row["program_id"], e["pattern"], e["kind"], e["asset_type"]) for e in entries])

    def _audit_ack(self, scan_id):
        with self.database.connect() as conn:
            row = conn.execute("SELECT p.slug FROM scan_run s JOIN program p ON p.id=s.program_id WHERE s.id=?", (scan_id,)).fetchone()
        audit(self.settings.BBASM_TARGETS / row["slug"] / "audit.jsonl", row["slug"], "ack", "automation_ack_by_user", scan_id=scan_id)

    def review(self, scan_id):
        if not self.database.path.exists():
            raise ScopeError("Scan not found", "scan_not_found")
        with self.database.connect() as conn:
            scan = conn.execute("SELECT * FROM scan_run WHERE id=?", (scan_id,)).fetchone()
            if scan is None:
                raise ScopeError("Scan not found", "scan_not_found")
            program = conn.execute("SELECT * FROM program WHERE id=?", (scan["program_id"],)).fetchone()
        stats = json.loads(scan["stats_json"] or "{}")
        policy = json.loads(program["policy_json"] or "{}")
        text = policy.get("policy_text") or (policy.get("program") or {}).get("policy") or policy.get("policy") or ""
        return {
            "scan": {key: scan[key] for key in ("id", "depth", "status", "trigger", "started_at", "finished_at", "error")},
            "slug": program["slug"], "source": program["source"], "handle": program["handle"],
            "target_path": str((self.settings.BBASM_TARGETS / program["slug"]).resolve()),
            **self.settings.hunt_target(program["slug"]),
            "trust": scope_trust(program["source"], program["handle"], policy),
            # The gate was computed from the data this very draft was resolved with.
            "launch_gate": stats.get("launch_gate") or launch_gate(program["source"], policy),
            "scope": stats.get("resolved_scope", []), "warnings": stats.get("warnings", []),
            "automation_ack": stats.get("automation_ack"),
            "policy": {"text": text if isinstance(text, str) else "", "source": policy.get("policy_source"),
                       "fetched_at": policy.get("fetched_at"), "user_text": policy.get("user_policy_text", ""),
                       "attempts": policy.get("attempts", []), "classification": policy.get("classification") or {}},
            "stats": {k: stats[k] for k in ("subs", "live", "urls", "findings", "observed", "diff") if k in stats},
        }

    def drafts(self):
        if not self.database.path.exists():
            return []
        with self.database.connect() as conn:
            rows = conn.execute("SELECT s.id,s.depth,s.stats_json,p.slug,p.source,c.created_at FROM scan_run s "
                                "JOIN program p ON p.id=s.program_id LEFT JOIN scan_config c ON c.scan_run_id=s.id "
                                "WHERE s.status='draft' ORDER BY s.id DESC").fetchall()
        result = []
        for row in rows:
            scope = json.loads(row["stats_json"] or "{}").get("resolved_scope") or []
            result.append({"id": row["id"], "slug": row["slug"], "source": row["source"], "depth": row["depth"],
                           "created_at": row["created_at"],
                           "in": sum(e["kind"] == "in" for e in scope), "out": sum(e["kind"] == "out" for e in scope)})
        return result

    def delete_draft(self, scan_id):
        if not self.database.path.exists():
            raise ScopeError("Scan not found", "scan_not_found")
        with self.database.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status,program_id FROM scan_run WHERE id=?", (scan_id,)).fetchone()
            if row is None:
                raise ScopeError("Scan not found", "scan_not_found")
            if row["status"] != "draft":
                raise ScopeError("Only draft scans can be deleted", "invalid_state")
            self._drop_draft(conn, scan_id, row["program_id"])

    @staticmethod
    def _drop_draft(conn, scan_id, program_id):
        conn.execute("DELETE FROM scan_config WHERE scan_run_id=?", (scan_id,))
        conn.execute("DELETE FROM scan_run WHERE id=?", (scan_id,))
        # A program that never ran anything and has no schedule is just leftover from an abandoned resolve.
        if not conn.execute("SELECT 1 FROM scan_run WHERE program_id=?", (program_id,)).fetchone() and \
                not conn.execute("SELECT 1 FROM schedule WHERE program_id=?", (program_id,)).fetchone():
            conn.execute("DELETE FROM scope_rule WHERE program_id=?", (program_id,))
            conn.execute("DELETE FROM program WHERE id=?", (program_id,))

    def purge_drafts(self, days=7):
        """Abandoned drafts never expire on their own; drop the old ones at boot."""
        if not self.database.path.exists():
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        with self.database.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute("SELECT s.id,s.program_id FROM scan_run s LEFT JOIN scan_config c ON c.scan_run_id=s.id "
                               "WHERE s.status='draft' AND COALESCE(c.created_at,'')<?", (cutoff,)).fetchall()
            for row in old:
                self._drop_draft(conn, row["id"], row["program_id"])
            return len(old)

    async def submit(self, scan_id, config=None, ack=False):
        if self.closing:
            raise ScopeError("Runner is shutting down")
        await asyncio.to_thread(self._enqueue, scan_id, config, ack)
        await self.adopt_queued(scan_id)

    async def adopt_queued(self, scan_id):
        """Attach an atomically persisted scheduled or manual queue entry."""
        if self.closing:
            raise ScopeError("Runner is shutting down")
        if scan_id in self.submitted:
            return
        if (await asyncio.to_thread(self.status, scan_id))["status"] != "queued":
            raise ScopeError("Only queued scans can enter the runner")
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
                if (await asyncio.to_thread(self.status, scan_id))["status"] != "queued":
                    return
                plan = await asyncio.to_thread(self.orchestrator.build, scan_id)
                if not await asyncio.to_thread(self._transition, scan_id, "running"):
                    return
                await asyncio.to_thread(self.diff_engine.capture, plan)
                for message in plan.warnings:
                    await self.logs.emit(scan_id, "log", level="warning", message=message)
                missing = self.orchestrator.missing_tools()
                for name in missing:
                    await self.logs.emit(scan_id, "log", level="warning", message=f"{name} missing; framework will skip unavailable tools")
                parser = ReconLogParser(self.settings)
                try:
                    await asyncio.wait_for(self._pipeline(plan, parser, errors),
                        min(plan.config.scan_timeout, self.settings.scan_timeout(plan.config.depth)))
                except asyncio.TimeoutError:
                    errors.append("Scan hard timeout exceeded")
                # _pipeline guarantees process cleanup before we inspect partial files.
                stats = await asyncio.to_thread(self.ingester.ingest, plan)
                stats["missing_tools"] = missing
                stats["monitor_findings"] = await asyncio.to_thread(self.monitors.ingest, plan)
                stats["findings"] = await asyncio.to_thread(self._finding_count, plan)
                stats["diff"] = await asyncio.to_thread(self.diff_engine.apply, plan,
                    stats.get("observations", {}), complete=not errors and bool(plan.commands))
                from backend.asm.ranking import rank_program
                await asyncio.to_thread(rank_program, self.database, plan.program_id, scan_id)
                await self._intel(plan, stats, parser)
                preview = "done_partial" if errors and stats.get("observed") else "failed" if errors else "done"
                if preview in {"done", "done_partial"}:
                    await asyncio.to_thread(self._transition, scan_id, preview, "; ".join(errors) or None, stats)
                    from backend.brief.generator import BriefGenerator
                    stats["brief"] = await asyncio.to_thread(BriefGenerator(self.settings, self.database).generate, plan.slug, scan_id)
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

    def _finding_count(self, plan):
        with self.database.connect() as conn:
            return conn.execute("SELECT count(*) FROM finding WHERE program_id=? AND last_seen_scan=?",
                                (plan.program_id, plan.scan_id)).fetchone()[0]

    async def _pipeline(self, plan, parser, errors):
        initial = list(plan.commands)
        if not initial and not plan.warnings:
            errors.append("No eligible recon commands")
        for command in initial:
            await self._command(plan, command, parser, errors)
        for command in self.orchestrator.discovered_commands(plan):
            await self._command(plan, command, parser, errors)
        for command in await asyncio.to_thread(self.monitors.commands, plan):
            await self._command(plan, command, parser, errors)

    async def _intel(self, plan, stats, parser):
        from backend.jobs.recon_orch import Command, recon_env
        tech = sorted({t for row in stats.get("observations", {}).values() for t in row.get("tech", [])})
        script = self.settings.tool_path("intel_engine.py")
        if not tech or not script.is_file():
            return
        errors = []
        command = Command([sys.executable, str(script), "--target", plan.slug, "--tech", ",".join(tech), "--json"],
                          recon_env(self.settings, plan.config, plan.root), plan.root, "intel", plan.slug)
        try:
            await asyncio.wait_for(self._command(plan, command, parser, errors, plan.root / "intel.json"), 15)
        except asyncio.TimeoutError:
            errors.append("Intel timeout (15 seconds)")
        for error in errors:
            await self.logs.emit(plan.scan_id, "log", level="warning", message=error)

    async def _command(self, plan, command, parser, errors, capture_path=None):
        process, capture, captured = None, None, 0
        try:
            self.egress.check(plan, command)
            if capture_path:
                if capture_path.is_symlink():
                    raise ValueError("Refusing capture symlink")
                capture = capture_path.open("wb")
            process = await self.process_factory(command)
            decoder, pending = codecs.getincrementaldecoder("utf-8")("replace"), ""
            while chunk := await process.stdout.read(4096):
                if capture is not None and captured < 1048576:
                    capture.write(chunk[:1048576 - captured])
                    captured += len(chunk)
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
            if capture is not None:
                capture.close()
            if process is not None:
                # Shield teardown so cancellation cannot leave grandchildren running.
                await asyncio.shield(self.stopper(process))

    async def cancel(self, scan_id):
        row = await asyncio.to_thread(self.status, scan_id)
        if row["status"] in {"done", "done_partial", "failed", "cancelled"}:
            return
        task = self.tasks.get(scan_id)
        if task is not None:
            if not task.cancelling():
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
