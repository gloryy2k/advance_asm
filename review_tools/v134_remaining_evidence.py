"""Read-only extraction of scan outcomes and stage timings; excludes policy/header values."""
import json
import sqlite3
import sys
from pathlib import Path

root = Path(sys.argv[1])
db = sqlite3.connect("file:" + (root / "data/bbasm.db").as_posix() + "?mode=ro", uri=True)
db.row_factory = sqlite3.Row
result = {"scans": [], "qa_schedule_enabled": None, "wolt_scope_rows": None}
for scan_id in (60, 61, 62, 63, 64, 65):
    row = db.execute("SELECT id,program_id,depth,status,trigger,started_at,finished_at,error,stats_json,baseline_scan_id FROM scan_run WHERE id=?", (scan_id,)).fetchone()
    assert row, scan_id
    stats = json.loads(row["stats_json"] or "{}")
    events = [json.loads(line) for line in (root / "data/logs" / f"{scan_id}.jsonl").read_text(encoding="utf-8").splitlines()]
    stages = [{k: e.get(k) for k in ("key", "status", "used_s", "budget_s", "ts")}
              for e in events if e.get("type") == "stage" and e.get("status") not in ("running", None)]
    result["scans"].append({"id": scan_id, "program_id": row["program_id"], "depth": row["depth"],
                            "status": row["status"], "trigger": row["trigger"],
                            "started_at": row["started_at"], "finished_at": row["finished_at"],
                            "error": row["error"],
                            "counts": {k: stats.get(k) for k in ("subs", "live", "urls", "findings", "baseline_scan_id")},
                            "diff": stats.get("diff"), "coverage": stats.get("coverage"),
                            "source_statuses": [{k: s.get(k) for k in ("source", "status", "seconds")}
                                                for s in stats.get("sources", [])],
                            "stages": stages})
result["qa_schedule_enabled"] = db.execute("""SELECT s.enabled FROM schedule s JOIN program p ON p.id=s.program_id
    WHERE p.slug='qa-v134-end2end-local'""").fetchone()[0]
result["wolt_scope_rows"] = db.execute("""SELECT count(*) FROM scope_rule s JOIN program p ON p.id=s.program_id
    WHERE p.slug='wolt'""").fetchone()[0]
out = Path("review_evidence/v134_fixcheck/remaining_scans.json")
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"saved": str(out), "statuses": [(x["id"], x["status"]) for x in result["scans"]],
                  "rank_64_s": next(event["used_s"] for scan in result["scans"] if scan["id"] == 64
                                    for event in scan["stages"] if event["key"] == "rank"),
                  "wolt_scope_rows": result["wolt_scope_rows"],
                  "qa_schedule_enabled": result["qa_schedule_enabled"]}, ensure_ascii=True))
