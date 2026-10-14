"""Durable pre-ingest baseline and idempotent, host-set diffs."""
import json

from backend.db import utc_now


class DiffEngine:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def _baseline_from_scan(conn, program_id, scan_id):
        """Hosts the last *completed* scan observed — immutable evidence, unlike the asset rows.

        Asset rows are overwritten by every ingest (partial, failed, or one that raced a cancel),
        so diffing against them could silently compare a scan with a half-finished neighbour.
        Returns (baseline_scan_id, {host: row}) or (None, None) when there is no usable scan.
        """
        for row in conn.execute("SELECT id,stats_json FROM scan_run WHERE program_id=? AND id<? "
                                "AND status IN ('done','done_partial') ORDER BY id DESC", (program_id, scan_id)):
            observations = json.loads(row["stats_json"] or "{}").get("observations")
            if isinstance(observations, dict) and observations:
                baseline = {host: {"host": host, "status_code": o.get("status_code"),
                                   "tech_json": json.dumps(o["tech"]) if "tech" in o else None, "state": "active"}
                            for host, o in observations.items()}
                # A host that disappeared earlier and is back now is a *change*, not a new asset.
                for gone in conn.execute("SELECT host,status_code,tech_json,state FROM asset WHERE program_id=? AND state='gone'", (program_id,)):
                    baseline.setdefault(gone["host"], dict(gone))
                return row["id"], baseline
        return None, None

    def capture(self, plan):
        with self.database.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            stats = json.loads(conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (plan.scan_id,)).fetchone()[0] or "{}")
            if "diff_baseline" not in stats and not stats.get("diff_complete"):
                baseline_id, baseline = self._baseline_from_scan(conn, plan.program_id, plan.scan_id)
                if baseline is None:  # first scan, or history that predates stored observations
                    baseline = {r["host"]: dict(r) for r in conn.execute(
                        "SELECT host,status_code,tech_json,state FROM asset WHERE program_id=?", (plan.program_id,))}
                stats["diff_baseline"] = baseline
                stats["baseline_scan_id"] = baseline_id
                conn.execute("UPDATE scan_run SET stats_json=?,baseline_scan_id=? WHERE id=?",
                             (json.dumps(stats), baseline_id, plan.scan_id))

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
                if (complete and plan.config.depth != "passive" and current.get("http_probed")
                        and not current.get("http_live")
                        and "status_code" not in current and before["state"] == "active"
                        and before["status_code"] is not None):
                    current["status_code"] = None
                    conn.execute("UPDATE asset SET status_code=NULL WHERE program_id=? AND host=?",
                                 (plan.program_id, host))
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
            stats.update(diff=counts, diff_complete=True, diff_compared_hosts=len(previous))
            stats.pop("diff_baseline", None)
            conn.execute("UPDATE scan_run SET stats_json=? WHERE id=?", (json.dumps(stats), plan.scan_id))
            return counts
