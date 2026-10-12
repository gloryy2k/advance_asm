"""Durable pre-ingest baseline and idempotent, host-set diffs."""
import json

from backend.db import utc_now


class DiffEngine:
    def __init__(self, database):
        self.database = database

    def capture(self, plan):
        with self.database.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            stats = json.loads(conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (plan.scan_id,)).fetchone()[0] or "{}")
            if "diff_baseline" not in stats and not stats.get("diff_complete"):
                stats["diff_baseline"] = {r["host"]: dict(r) for r in conn.execute(
                    "SELECT host,status_code,tech_json,state FROM asset WHERE program_id=?", (plan.program_id,))}
                conn.execute("UPDATE scan_run SET stats_json=? WHERE id=?", (json.dumps(stats), plan.scan_id))

    def apply(self, plan, observations, *, complete):
        with self.database.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            stats = json.loads(conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (plan.scan_id,)).fetchone()[0] or "{}")
            if stats.get("diff_complete"):
                return stats["diff"]
            if "diff_baseline" not in stats:
                raise ValueError("Capture diff baseline before ingestion")
            previous = stats["diff_baseline"]
            counts = {"new": 0, "changed": 0, "gone": 0}

            def event(host, change, detail):
                conn.execute("INSERT INTO diff_event(program_id,scan_run_id,entity,entity_ref,change,detail_json,created_at) VALUES(?,?,'asset',?,?,?,?)",
                             (plan.program_id, plan.scan_id, host, change, json.dumps(detail), utc_now()))
                counts[change] += 1

            for host, current in observations.items():
                before = previous.get(host)
                if before is None:
                    event(host, "new", {"after": current})
                    continue
                changes = {}
                if before["state"] == "gone":
                    changes["state"] = {"before": "gone", "after": "active"}
                if "status_code" in current and current["status_code"] != before["status_code"]:
                    changes["status_code"] = {"before": before["status_code"], "after": current["status_code"]}
                if "tech" in current:
                    old = sorted({str(t).lower() for t in json.loads(before["tech_json"] or "[]")})
                    new = sorted({str(t).lower() for t in current["tech"]})
                    if old != new:
                        changes["tech"] = {"before": old, "after": new}
                if changes:
                    event(host, "changed", changes)
            # Partial/error scans cannot prove absence. Reduced review scope cannot
            # retire assets outside this scan's approved gate either.
            if complete:
                for host, before in previous.items():
                    if host not in observations and before["state"] == "active" and plan.gate.in_scope(host):
                        event(host, "gone", {"before": before})
                        conn.execute("UPDATE asset SET state='gone' WHERE program_id=? AND host=?", (plan.program_id, host))
            stats.update(diff=counts, diff_complete=True)
            stats.pop("diff_baseline", None)
            conn.execute("UPDATE scan_run SET stats_json=? WHERE id=?", (json.dumps(stats), plan.scan_id))
            return counts
