"""APScheduler jobs restored from the spec's SQLite schedule table at boot."""
from datetime import datetime, timedelta, timezone
import json

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.db import utc_now
from backend.jobs.runner import store_config
from backend.jobs.scope_resolver import ScopeError, classify
from backend.models import ScanConfig
from backend.scope_gate import audit

INTERVALS = {"6h": 21600, "daily": 86400, "weekly": 604800}


class ScanScheduler:
    def __init__(self, settings, database, runner):
        self.settings, self.database, self.runner = settings, database, runner
        self.scheduler = AsyncIOScheduler(timezone="UTC")

    def configure(self, program_id, interval, config, enabled=True):
        if interval not in INTERVALS:
            raise ScopeError("interval must be 6h, daily or weekly")
        config = ScanConfig.model_validate(config)
        self.runner._validate(config)
        next_run = datetime.now(timezone.utc) + timedelta(seconds=INTERVALS[interval])
        with self.database.connect() as conn, conn:
            if not conn.execute("SELECT id FROM program WHERE id=?", (program_id,)).fetchone():
                raise ScopeError("Program not found")
            conn.execute("INSERT INTO schedule(program_id,interval,depth,enabled,config_json,next_run_at,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(program_id) DO UPDATE SET interval=excluded.interval,depth=excluded.depth,enabled=excluded.enabled,config_json=excluded.config_json,next_run_at=excluded.next_run_at,last_error=NULL,last_error_at=NULL",
                         (program_id, interval, config.depth, int(enabled), config.model_dump_json(), next_run.isoformat(), utc_now()))
            row = dict(conn.execute("SELECT * FROM schedule WHERE program_id=?", (program_id,)).fetchone())
        self._install(row)
        return row

    def _install(self, row):
        job_id = f"program-{row['program_id']}"
        if not row["enabled"]:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            return
        self.scheduler.add_job(self.dispatch, "interval", seconds=INTERVALS[row["interval"]],
            id=job_id, args=[row["program_id"]], replace_existing=True,
            next_run_time=datetime.fromisoformat(row["next_run_at"]), coalesce=True,
            max_instances=1, misfire_grace_time=None)

    def start(self):
        if self.database.path.exists():
            with self.database.connect() as conn:
                rows = [dict(r) for r in conn.execute("SELECT * FROM schedule WHERE enabled=1")]
            for row in rows:
                # Validate stored config on boot as well as on dispatch.
                config = ScanConfig.model_validate_json(row["config_json"])
                self.runner._validate(config)
                self._install(row)
        self.scheduler.start()

    async def close(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def dispatch(self, program_id):
        if self.runner.closing:
            return None
        from backend.api.scans import require_apex, require_ffuf, require_gate, require_headers
        from backend.scope_selection import apply_selection, read_selection
        from backend.trust import launch_gate, required_headers
        now = datetime.now(timezone.utc)
        problem = None
        with self.database.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM schedule WHERE program_id=?", (program_id,)).fetchone()
            if not row or not row["enabled"] or datetime.fromisoformat(row["next_run_at"]) > now:
                return None
            config = ScanConfig.model_validate_json(row["config_json"])
            if config.depth != row["depth"]:
                raise ScopeError("Schedule depth differs from stored config")
            program = conn.execute("SELECT * FROM program WHERE id=?", (program_id,)).fetchone()
            if program is None or program["archived_at"] or program["deleting_at"]:
                return None          # an archived program runs nothing in the background
            entries = [classify(r["pattern"], r["kind"], r["asset_type"])
                       for r in conn.execute("SELECT * FROM scope_rule WHERE program_id=?", (program_id,))]
            # What the user excluded at Review is the program's choice now; an unattended run must not bring it back.
            config = apply_selection(config, entries, read_selection(program["scope_selection_json"]))
            self.runner._validate(config)
            previous = datetime.fromisoformat(row["next_run_at"])
            step = INTERVALS[row["interval"]]
            next_run = previous + timedelta(seconds=(int((now - previous).total_seconds() // step) + 1) * step)
            conn.execute("UPDATE schedule SET next_run_at=? WHERE id=?", (next_run.isoformat(), row["id"]))
            # The program's scope/policy may have changed since the schedule was enabled; re-check what Review checked.
            policy = json.loads(program["policy_json"] or "{}")
            try:
                require_gate(config.depth, launch_gate(program["source"], policy))
                require_headers(config, required_headers(policy))
                require_ffuf(config)
                require_apex(config)
            except ScopeError as exc:
                problem = exc
                conn.execute("UPDATE schedule SET last_error=?,last_error_at=? WHERE id=?", (str(exc)[:500], utc_now(), row["id"]))
            else:
                conn.execute("UPDATE schedule SET last_error=NULL,last_error_at=NULL WHERE id=?", (row["id"],))
                if conn.execute("SELECT 1 FROM scan_run WHERE program_id=? AND status IN ('queued','running')", (program_id,)).fetchone():
                    return None  # Coalesce overlapping scans; never pile up a backlog.
                entries_json = [e.model_dump() for e in entries]
                if not any(e["kind"] == "in" for e in entries_json):
                    raise ScopeError("Scheduled scope is empty")
                slug = program["slug"]
                scan_id = conn.execute("INSERT INTO scan_run(program_id,depth,status,trigger,stats_json) VALUES(?,?,'queued','scheduled',?)",
                                       (program_id, config.depth, json.dumps({"resolved_scope": entries_json}))).lastrowid
                conn.execute("INSERT INTO scan_config(scan_run_id,created_at) VALUES(?,?)", (scan_id, utc_now()))
                store_config(conn, scan_id, config)
                target = (self.settings.BBASM_TARGETS / slug).resolve()
                if not target.is_relative_to(self.settings.BBASM_TARGETS.resolve()):
                    raise ScopeError("Scheduled target escapes target root")
                audit(target / "audit.jsonl", slug, "queued", "scheduled_scan", scan_id=scan_id)
        if problem is not None:
            raise problem   # recorded on the schedule above (committed), then reported to the scheduler log
        self.runner._audit_headers(scan_id, config)
        await self.runner.adopt_queued(scan_id)
        return scan_id
