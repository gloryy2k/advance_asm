"""Bounded asyncio job queue; subprocess groups, cancellation and partial output."""

import asyncio
import functools
import time
from concurrent.futures import ThreadPoolExecutor
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
from backend.trust import launch_gate, required_headers, scope_trust


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
        # Scan work and control actions get their own threads: web requests share the default pool, and a backlog of slow
        # report requests must never be able to queue a Cancel behind itself.
        self.executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="bbasm-run")
        self.control_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bbasm-ctl")
        self.queue, self.workers, self.tasks = asyncio.Queue(), [], {}
        self.submitted, self.program_locks = set(), {}
        self.closing = False

    async def _thread(self, func, *args):
        return await asyncio.get_running_loop().run_in_executor(self.executor, functools.partial(func, *args))

    async def _ctl(self, func, *args, timeout=8):
        """Control-plane call (status/cancel): its own threads and a hard bound, so it cannot hang behind scan work."""
        return await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(self.control_executor, functools.partial(func, *args)), timeout)

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
                normalize_pattern(pattern, deny=True)   # same rule the gate applies to an OUT entry
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
            self._apply_scope_snapshot(conn, scan_id, config)
            stats = json.loads(conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (scan_id,)).fetchone()["stats_json"] or "{}")
            if ack:  # same transaction as queueing: a fast worker can never run before the confirmation is stored
                stats["automation_ack"] = utc_now()
            from backend.templates import snapshot_for_scan
            templates = snapshot_for_scan(self.settings, config)
            if templates is not None:
                stats["nuclei_templates"] = templates      # the exact template set this scan is run with
            conn.execute("UPDATE scan_run SET stats_json=? WHERE id=?", (json.dumps(stats), scan_id))
            conn.execute("UPDATE scan_run SET status='queued' WHERE id=?", (scan_id,))
        if ack:
            self._audit_ack(scan_id)
        self._audit_headers(scan_id, config)

    def _audit_headers(self, scan_id, config):
        """What the policy asked for, what is sent and what the user knowingly skipped. Names only, never values."""
        if config.depth == "passive":
            return
        with self.database.connect() as conn:
            row = conn.execute("SELECT p.slug,p.policy_json FROM scan_run s JOIN program p ON p.id=s.program_id WHERE s.id=?", (scan_id,)).fetchone()
        required = required_headers(json.loads(row["policy_json"] or "{}"))
        sent = [h.split(":", 1)[0].strip() for h in config.request_headers]
        if not (required or sent):
            return
        skipped = [n for n in required if n.lower() not in {s.lower() for s in sent}]
        audit(self.settings.BBASM_TARGETS / row["slug"] / "audit.jsonl", row["slug"], "allow" if not skipped else "ack",
              "request_headers", scan_id=scan_id, required=required, sent=sent, skipped=skipped)

    @staticmethod
    def _apply_scope_snapshot(conn, scan_id, config=None):
        """Launch is the moment the reviewed scope becomes the program's scope (schedules read it) -- including what the
        user un-ticked or excluded by hand, so Rescan and schedules do not quietly bring it back."""
        row = conn.execute("SELECT program_id,stats_json FROM scan_run WHERE id=?", (scan_id,)).fetchone()
        stats = json.loads(row["stats_json"] or "{}")
        entries = stats.get("resolved_scope") or []
        # Launching is the user's explicit decision to work on this program again: an archived one comes back.
        conn.execute("UPDATE program SET archived_at=NULL WHERE id=? AND archived_at IS NOT NULL", (row["program_id"],))
        if not entries:
            return
        if stats.get("policy_snapshot") is not None:
            # Scope and policy travel together: launching a draft makes ITS policy the program's, like its scope.
            conn.execute("UPDATE program SET policy_json=?,updated_at=? WHERE id=?",
                         (json.dumps(stats["policy_snapshot"]), utc_now(), row["program_id"]))
        if config is not None:
            from backend.scope_selection import selection_from_config
            conn.execute("UPDATE program SET scope_selection_json=? WHERE id=?",
                         (json.dumps(selection_from_config(entries, config)), row["program_id"]))
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
        # A draft is judged against the policy it was resolved with; the program's current policy is only used for
        # drafts and scans that predate snapshots.
        policy = stats.get("policy_snapshot")
        if policy is None:
            policy = json.loads(program["policy_json"] or "{}")
        newer = None
        if scan["status"] == "draft" and stats.get("policy_snapshot_at") and (program["updated_at"] or "") > stats["policy_snapshot_at"]:
            with self.database.connect() as conn:
                newer = conn.execute("SELECT max(id) FROM scan_run WHERE program_id=? AND status='draft' AND id>?",
                                     (scan["program_id"], scan_id)).fetchone()[0] or 0
        text = policy.get("policy_text") or (policy.get("program") or {}).get("policy") or policy.get("policy") or ""
        return {
            "scan": {key: scan[key] for key in ("id", "depth", "status", "trigger", "started_at", "finished_at", "error")},
            "slug": program["slug"], "source": program["source"], "handle": program["handle"],
            "target_path": str((self.settings.BBASM_TARGETS / program["slug"]).resolve()),
            **self.settings.hunt_target(program["slug"]),
            "trust": scope_trust(program["source"], program["handle"], policy),
            # The gate was computed from the data this very draft was resolved with.
            "launch_gate": stats.get("launch_gate") or launch_gate(program["source"], policy),
            "request_header_hints": required_headers(policy),
            # set when the program has been re-resolved or another draft launched since this draft was made
            "policy_newer": newer is not None, "newest_draft": newer or None,
            "archived": bool(program["archived_at"]),
            "scope": stats.get("resolved_scope", []), "warnings": stats.get("warnings", []),
            "automation_ack": stats.get("automation_ack"),
            "policy": {"text": text if isinstance(text, str) else "", "source": policy.get("policy_source"),
                       "fetched_at": policy.get("fetched_at"), "user_text": policy.get("user_policy_text", ""),
                       "attempts": policy.get("attempts", []), "completeness": policy.get("completeness"), "classification": policy.get("classification") or {}},
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

    def delete_drafts(self, ids):
        deleted, skipped = [], []
        if not self.database.path.exists():
            return {"deleted": [], "skipped": [{"id": i, "reason": "not_found"} for i in ids]}
        with self.database.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            for scan_id in dict.fromkeys(ids):
                row = conn.execute("SELECT status,program_id FROM scan_run WHERE id=?", (scan_id,)).fetchone()
                if row is None:
                    skipped.append({"id": scan_id, "reason": "not_found"})
                elif row["status"] != "draft":
                    skipped.append({"id": scan_id, "reason": "not_draft"})   # launched meanwhile: never touched
                else:
                    self._drop_draft(conn, scan_id, row["program_id"])
                    deleted.append(scan_id)
        return {"deleted": deleted, "skipped": skipped}

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
                               "WHERE s.status='draft' AND c.created_at IS NOT NULL AND c.created_at<?", (cutoff,)).fetchall()
            for row in old:
                self._drop_draft(conn, row["id"], row["program_id"])
            return len(old)

    async def submit(self, scan_id, config=None, ack=False):
        if self.closing:
            raise ScopeError("Runner is shutting down")
        await self._thread(self._enqueue, scan_id, config, ack)
        await self.adopt_queued(scan_id)

    async def adopt_queued(self, scan_id):
        """Attach an atomically persisted scheduled or manual queue entry."""
        if self.closing:
            raise ScopeError("Runner is shutting down")
        if scan_id in self.submitted:
            return
        if (await self._thread(self.status, scan_id))["status"] != "queued":
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
                await self._thread(self._transition, scan_id, "failed", f"Worker error: {type(exc).__name__}")
            finally:
                self.tasks.pop(scan_id, None)
                self.submitted.discard(scan_id)
                self.queue.task_done()

    async def _execute(self, scan_id):
        plan, stats, errors, cancelled = None, {}, [], False
        try:
            row = await self._thread(self.status, scan_id)
            lock = self.program_locks.setdefault(row["program_id"], asyncio.Lock())
            async with lock:
                if (await self._thread(self.status, scan_id))["status"] != "queued":
                    return
                plan = await self._thread(self.orchestrator.build, scan_id)
                if not await self._thread(self._transition, scan_id, "running"):
                    return
                await self._thread(self._banner, plan.slug, scan_id, "running", plan.config.depth)
                await self._thread(self.diff_engine.capture, plan)
                for message in plan.warnings:
                    await self.logs.emit(scan_id, "log", level="warning", message=message)
                missing = self.orchestrator.missing_tools()
                from backend.asm.phases import tools_needed
                needed = tools_needed(plan.config, self.settings)
                for name in missing:
                    if name in needed:
                        hint = " (nuclei KHÔNG được chạy và BBASM chặn tự tải template; chạy `nuclei -update-templates` hoặc đặt BBASM_UPDATE_TEMPLATES=1 rồi khởi động lại)" if name == "nuclei-templates" else ""
                        await self.logs.emit(scan_id, "log", level="warning", tag="missing_tool",
                                             message=f"Thiếu {name}: các bước dùng nó sẽ bị bỏ qua{hint}")
                    else:   # not used by this configuration (e.g. ffuf below Strong): not a problem, only noted
                        await self.logs.emit(scan_id, "log", tag="not_needed", message=f"{name} chưa cài — không dùng ở cấu hình này")
                parser = ReconLogParser(self.settings, plan.config)
                total = min(plan.config.scan_timeout, self.settings.scan_timeout(plan.config.depth))
                try:
                    await asyncio.wait_for(self._pipeline(plan, parser, errors, total), total)
                except asyncio.TimeoutError:
                    errors.append("Scan hard timeout exceeded")
                    for stage in plan.stages:
                        if stage["status"] == "running":
                            stage["status"] = "timeout"
                # _pipeline guarantees process cleanup before we inspect partial files.
                # Everything after the pipeline is announced and bounded: a silent step used to look exactly like a hang.
                stats = await self._post(plan, "ingest", "Nạp dữ liệu vào DB", self.ingester.ingest, plan, timeout=self.POST_LIMITS["ingest"])
                stats["missing_tools"] = missing
                stats["missing_needed"] = sorted(set(missing) & needed)
                stats["stages"], stats["sources"], stats["tool_notes"] = plan.stages, plan.sources, plan.tool_notes
                plan.coverage["unprobed"] = max(0, plan.coverage["discovered"] - plan.coverage["probed"])
                stats["coverage"] = plan.coverage
                # Hosts nobody got an answer from (cut off or never reached): kept so a later run can be pointed at exactly these.
                stats["unprobed_hosts"] = [h for h in plan.discovered_hosts if h not in plan.probed_hosts][:2000]
                stats["path_rule_hosts"] = plan.path_rules
                stats["asset_coverage"], stats["manual_assets"] = plan.asset_coverage, plan.manual_assets
                stats["request_headers"] = [h.partition(":")[0] for h in plan.config.request_headers]  # names only, never values
                stats["monitor_findings"] = await self._post(plan, "monitors", "Nạp kết quả monitor", self.monitors.ingest, plan, timeout=self.POST_LIMITS["monitors"], soft=errors, default=0)
                if plan.takeover_summary:
                    stats["takeover"] = plan.takeover_summary
                stats["findings"] = await self._thread(self._finding_count, plan)
                complete = not errors and bool(plan.commands) and plan.coverage["unprobed"] == 0
                stats["diff"] = await self._post(plan, "diff", "So sánh với scan trước", self._diff, plan, stats.get("observations", {}), complete,
                                                 timeout=self.POST_LIMITS["diff"], soft=errors, default={"new": 0, "changed": 0, "gone": 0})
                from backend.asm.ranking import rank_program
                await self._post(plan, "rank", "Xếp hạng bề mặt", rank_program, self.database, plan.program_id, scan_id, timeout=self.POST_LIMITS["rank"], soft=errors)
                await self._intel(plan, stats, parser)
                preview = "done_partial" if errors and stats.get("observed") else "failed" if errors else "done"
                if preview in {"done", "done_partial"}:
                    await self._thread(self._transition, scan_id, preview, "; ".join(errors) or None, stats)
                    from backend.brief.generator import BriefGenerator
                    stats["brief"] = await self._post(plan, "brief", "Tạo AGENT_BRIEF.md", BriefGenerator(self.settings, self.database).generate, plan.slug, scan_id,
                                                      timeout=self.POST_LIMITS["brief"], soft=errors, default=None)
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
        await self._finalize(scan_id, status, "; ".join(errors)[:2000] or None, stats)
        if plan and status in {"failed", "cancelled"}:
            await self._thread(self._banner, plan.slug, scan_id, status, plan.config.depth)
        if plan:
            audit(plan.audit_path, plan.slug, status, "scan_finished", scan_id=scan_id)
        await self.logs.emit(scan_id, "done", status=status, stats=stats, error="; ".join(errors)[:2000] or None)

    # Upper bound (seconds) for each step after the pipeline. A step that exceeds it stops being waited for: the scan
    # reaches a terminal state with the reason in its error instead of staying "running" forever.
    POST_LIMITS = {"ingest": 900, "monitors": 120, "diff": 300, "rank": 300, "brief": 120}

    def _diff(self, plan, observations, complete):
        return self.diff_engine.apply(plan, observations, complete=complete)

    async def _post(self, plan, key, label, func, *args, timeout, soft=None, default=None):
        """Run one blocking step off the event loop with a progress event, timing and a hard bound.

        soft=None: the step is essential, a timeout aborts the scan (status failed with the reason).
        soft=<errors list>: the scan continues without this step and says so in its errors."""
        scan_id = plan.scan_id
        await self.logs.emit(scan_id, "stage", key=key, label=label, status="running", message=f"▶ {label}")
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(self._thread(func, *args), timeout)
        except asyncio.TimeoutError:
            reason = f"Bước '{label}' quá {timeout}s (timeout); không chờ thêm"
            await self.logs.emit(scan_id, "stage", key=key, label=label, status="timeout", message=f"■ {label}: timeout sau {timeout}s")
            if soft is None:
                raise RuntimeError(reason) from None
            soft.append(reason)
            return default
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if soft is None:
                raise
            soft.append(f"Bước '{label}' lỗi: {type(exc).__name__}: {str(exc)[:200]}")
            await self.logs.emit(scan_id, "stage", key=key, label=label, status="error", message=f"■ {label}: lỗi {type(exc).__name__}")
            return default
        await self.logs.emit(scan_id, "stage", key=key, label=label, status="ok", used_s=round(time.monotonic() - started, 1),
                             message=f"■ {label}: xong sau {time.monotonic() - started:.1f}s")
        return result

    async def _finalize(self, scan_id, status, error, stats):
        """The last write of a scan. A busy database must never leave it "running": retry, then give up loudly."""
        for attempt in range(4):
            try:
                await self._thread(self._transition, scan_id, status, error, stats)
                return
            except Exception as exc:
                if attempt == 3:
                    await self.logs.emit(scan_id, "log", level="error", message=f"Không ghi được trạng thái cuối ({type(exc).__name__})")
                    raise
                await asyncio.sleep(1 + attempt)

    def _banner(self, slug, scan_id, status, depth):
        """Tell readers of AGENT_BRIEF.md which scan the file belongs to while a newer one runs or after it failed."""
        from backend.brief.generator import BriefGenerator
        text = {"running": f"⏳ Scan #{scan_id} ({depth}) đang chạy. Nội dung bên dưới là của scan TRƯỚC, không phải scan này.",
                "failed": f"⚠ Scan #{scan_id} ({depth}) thất bại, chưa có brief mới. Nội dung bên dưới là của scan trước.",
                "cancelled": f"⚠ Scan #{scan_id} ({depth}) đã bị huỷ, chưa có brief mới. Nội dung bên dưới là của scan trước."}[status]
        try:
            BriefGenerator(self.settings, self.database).set_banner(slug, text)
        except Exception:   # a brief problem must never stop or fail the scan itself
            pass

    def _finding_count(self, plan):
        with self.database.connect() as conn:
            return conn.execute("SELECT count(*) FROM finding WHERE program_id=? AND last_seen_scan=?",
                                (plan.program_id, plan.scan_id)).fetchone()[0]

    # Cumulative share of the scan budget by which each stage must be finished. Unused time rolls forward, an overrun
    # is cut at its deadline so later stages (probing what discovery found) always get their turn.
    STAGES = {"passive": (("discovery", 0.90),),
              # Probing (liveness only, no port scan) is cheap; the deep pass (crawl, templates, nmap, ffuf) is where time is spent.
              # Unused time of a stage rolls forward, so these are ceilings, not allowances.
              "active": (("discovery", 0.25), ("main", 0.45), ("probe", 0.62), ("deep", 0.95))}
    STAGE_LABELS = {"discovery": "Khám phá subdomain/URL", "main": "Host nêu trong scope", "probe": "Probe host đã khám phá",
                    "deep": "Quét sâu host đang sống", "monitor": "Theo dõi JS/secret"}

    async def _stage(self, plan, key, commands, deadline, parser, errors, on_success=None):
        label = self.STAGE_LABELS[key]
        record = {"key": key, "label": label, "status": "running", "budget_s": 0, "used_s": 0, "commands": len(commands),
                  "commands_ok": 0, "commands_timeout": 0, "commands_skipped": 0}
        plan.stages.append(record)
        if not commands:
            record["status"] = "empty"
            return
        started = time.monotonic()
        remaining = deadline - started
        record["budget_s"] = max(0, int(remaining))
        if remaining <= 0:
            record["status"] = "skipped_budget"
            record["commands_skipped"] = len(commands)
            for command in commands:
                command.status = "skipped"
            errors.append(f"Giai đoạn '{label}' không chạy: hết ngân sách thời gian")
            await self.logs.emit(plan.scan_id, "stage", key=key, label=label, status="skipped_budget",
                                 message=f"▶ {label}: bỏ qua vì hết ngân sách thời gian")
            return
        await self.logs.emit(plan.scan_id, "stage", key=key, label=label, status="running", commands=len(commands),
                             budget_s=record["budget_s"], message=f"▶ {label}: {len(commands)} lệnh, tối đa {record['budget_s']}s")
        failures = len(errors)

        async def run():
            for index, command in enumerate(commands):
                # One command may not eat the whole stage: it gets its fair share of what is left, with some room to borrow, so a
                # slow batch is cut (its output so far is kept) and the next one still gets its turn.
                left = max(1.0, deadline - time.monotonic())
                after = len(commands) - index
                cap = left if after == 1 else min(left, (left / after) * 1.5)
                command.status = "running"
                began = time.monotonic()
                try:
                    ok = await asyncio.wait_for(self._command(plan, command, parser, errors), cap)
                    command.status = "ok" if ok else "error"
                except asyncio.TimeoutError:
                    command.status, ok = "timeout", False
                    record["commands_timeout"] += 1
                    errors.append(f"Giai đoạn '{label}': lệnh {index + 1}/{len(commands)} dừng sau {int(cap)}s (giới hạn từng lệnh); phần kết quả đã có vẫn được nhập")
                    await self.logs.emit(plan.scan_id, "stage", key=key, label=label, status="command_timeout",
                                         message=f"■ {label}: lệnh {index + 1}/{len(commands)} dừng sau {int(cap)}s — tiếp tục lệnh sau")
                command.used_s = int(time.monotonic() - began)
                if command.status == "ok":
                    record["commands_ok"] += 1
                if ok and on_success:
                    on_success(command)

        try:
            await asyncio.wait_for(run(), remaining)
            record["status"] = "error" if len(errors) > failures else "ok"
        except asyncio.TimeoutError:
            record["status"] = "timeout"
            errors.append(f"Giai đoạn '{label}' hết ngân sách {record['budget_s']}s (timeout); dữ liệu dở dang vẫn được nhập")
        for command in commands:
            if command.status == "running":
                command.status = "timeout"
                record["commands_timeout"] += 1
            elif command.status == "pending":
                command.status = "skipped"
                record["commands_skipped"] += 1
        record["used_s"] = int(time.monotonic() - started)
        await self.logs.emit(plan.scan_id, "stage", key=key, label=label, status=record["status"], used_s=record["used_s"],
                             message=f"■ {label}: {record['status']} sau {record['used_s']}s")

    async def _pipeline(self, plan, parser, errors, total=None):
        total = total or plan.config.scan_timeout
        started = time.monotonic()
        shares = dict(self.STAGES["passive" if plan.config.depth == "passive" else "active"])
        initial = list(plan.commands)
        if not initial and not plan.warnings:
            errors.append("No eligible recon commands")
        def deadline(key):
            return started + total * shares.get(key, 1.0)

        plan_batches = []

        def done(command):
            self.orchestrator.refresh_coverage(plan, plan_batches)

        await self._stage(plan, "discovery", [c for c in initial if c.stage == "discovery"], deadline("discovery"), parser, errors)
        await self._stage(plan, "main", [c for c in initial if c.stage != "discovery"], deadline("main"), parser, errors)
        if plan.config.depth != "passive":
            hosts = await self._thread(self.orchestrator.discovered_hosts, plan)
            batches = await self._thread(self.orchestrator.probe_batches, plan, hosts)
            plan_batches[:] = batches
            await self._stage(plan, "probe", batches, deadline("probe"), parser, errors, on_success=done)
            await self._thread(self.orchestrator.refresh_coverage, plan, batches)     # also counts hosts that answered in a batch that was cut off
            deep = await self._thread(self.orchestrator.deep_command, plan, batches)
            await self._stage(plan, "deep", [deep] if deep else [], deadline("deep"), parser, errors)
        await self._stage(plan, "monitor", await self._thread(self.monitors.commands, plan), started + total, parser, errors)

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
        process, capture, captured, ok = None, None, 0, False
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
            else:
                ok = True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            errors.extend(await self._collect_sources(plan, command))
            if capture is not None:
                capture.close()
            if process is not None:
                # Shield teardown so cancellation cannot leave grandchildren running.
                await asyncio.shield(self.stopper(process))
        return ok

    async def _collect_sources(self, plan, command):
        """Say which passive source failed or timed out; the data it already produced is still imported."""
        from backend.jobs.recon_orch import read_source_status
        names = {"timeout": "quá thời gian", "error": "lỗi"}
        problems = []
        from backend.jobs.recon_orch import read_tool_notes
        for note in await self._thread(read_tool_notes, command.output):
            if note not in plan.tool_notes:
                plan.tool_notes.append(note)
                await self.logs.emit(plan.scan_id, "log", level="warning", tag="skipped_config", message=f"{note['tool']}: {note['note']}")
        for row in await self._thread(read_source_status, command.output):
            plan.sources.append({**row, "stage": command.stage})
            if row["status"] != "ok":
                text = f"Nguồn {row['source']} {names[row['status']]} sau {row['seconds']}s"
                problems.append(text + " (kết quả dở dang vẫn được dùng)")
                await self.logs.emit(plan.scan_id, "log", level="warning", message=text + " — vẫn dùng kết quả dở dang đã có")
        return problems

    async def cancel(self, scan_id):
        """Always returns promptly: it uses the control threads, bounds every wait, and writes the terminal state itself
        when the scan's own coroutine cannot (blocked on a slow disk or a locked database)."""
        row = await self._ctl(self.status, scan_id)
        if row["status"] in {"done", "done_partial", "failed", "cancelled"}:
            return
        task = self.tasks.get(scan_id)
        if task is not None:
            if not task.cancelling():
                task.cancel()
            try:   # the task normally ends within a moment; if it is stuck in a worker thread we stop waiting
                await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 5)
            except asyncio.TimeoutError:
                pass
            # A Task cancelled before its coroutine starts never enters _execute's exception handler, and one stuck in a
            # thread may not get to its final write. Persist cancellation here as well.
            if (await self._ctl(self.status, scan_id))["status"] in {"queued", "running"}:
                await self._ctl(self._transition, scan_id, "cancelled")
                await self.logs.emit(scan_id, "done", status="cancelled")
        else:
            self.submitted.discard(scan_id)
            await self._ctl(self._transition, scan_id, "cancelled")
            await self.logs.emit(scan_id, "done", status="cancelled")

    async def close(self):
        self.closing = True
        for scan_id in list(self.submitted):
            await self.cancel(scan_id)
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.control_executor.shutdown(wait=False, cancel_futures=True)
        await asyncio.to_thread(self.logs.flush)   # the journal is complete when close() returns
