"""Corrections to results stored by an older version, applied once at start-up (idempotent) and recorded on the scan.

A fix to a parser does nothing for a scan that already ran. These rewrite what the old parser stored, using the scan's own
output files when they are still on disk, and say so on the scan (`stats.repairs`) so no number changes silently."""
import json
import logging

from backend.asm.takeover import parse_subjack
from backend.db import utc_now
from backend.jobs.ingest import lines

log = logging.getLogger("bbasm.repair")
OLD_NAME = "subjack.txt:candidate"


def _backup(database, label):
    """A consistent copy before rewriting stored results (the same mechanism a schema upgrade uses)."""
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    target = database.path.with_name(f"{database.path.name}.pre-repair-{label}-{stamp}")
    with database.connect() as conn:
        destination = __import__("sqlite3").connect(target)
        try:
            conn.backup(destination)
        finally:
            destination.close()
    old = sorted(database.path.parent.glob(f"{database.path.name}.pre-repair-*"))[:-3]
    for path in old:
        path.unlink(missing_ok=True)


def repair_takeover(database, settings):
    """v1.6.0: every line of subjack.txt (`[Not Vulnerable] host` included) used to be stored as a High takeover."""
    done = []
    with database.connect() as conn:
        groups = conn.execute(
            "SELECT f.program_id pid, f.last_seen_scan scan, p.slug slug, count(*) n FROM finding f JOIN program p ON p.id=f.program_id "
            "WHERE f.type='takeover' AND f.name=? GROUP BY f.program_id, f.last_seen_scan", (OLD_NAME,)).fetchall()
    if groups:
        _backup(database, "takeover")
    for group in groups:
        path = settings.BBASM_TARGETS / group["slug"] / "recon" / "scans" / str(group["scan"]) / "monitors" / "takeover" / "subjack.txt"
        have_file = path.is_file() and not path.is_symlink()
        candidates, clean, _ = parse_subjack(lines(path)) if have_file else ([], 0, 0)
        services = {}
        for host, service in candidates:
            services.setdefault(host.lower(), service)
        removed = kept = flagged = 0
        with database.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT f.id, f.asset_id, a.host FROM finding f LEFT JOIN asset a ON a.id=f.asset_id "
                                "WHERE f.program_id=? AND f.last_seen_scan=? AND f.type='takeover' AND f.name=?",
                                (group["pid"], group["scan"], OLD_NAME)).fetchall()
            for row in rows:
                host = (row["host"] or "").lower()
                if not have_file:
                    # Nothing to check against: keep the row visible but never as a High takeover.
                    conn.execute("UPDATE finding SET severity='info', detail_json=? WHERE id=?",
                                 (json.dumps({"source": "subjack", "candidate": True, "verified": False, "legacy_unreliable": True,
                                              "note": "Kết quả cũ từ trình phân tích lỗi (mọi dòng subjack bị tính là ứng viên); không còn file subjack.txt để kiểm lại."}), row["id"]))
                    flagged += 1
                elif host in services:
                    service = services[host]
                    clash = conn.execute("SELECT id FROM finding WHERE program_id=? AND type='takeover' AND name=? AND asset_id=? AND id!=?",
                                         (group["pid"], f"subjack:{service}", row["asset_id"], row["id"])).fetchone()
                    if clash:
                        conn.execute("DELETE FROM finding WHERE id=?", (row["id"],))
                    else:
                        conn.execute("UPDATE finding SET name=?, severity='medium', detail_json=? WHERE id=?",
                                     (f"subjack:{service}", json.dumps({"source": "subjack", "candidate": True, "verified": False, "service": service}), row["id"]))
                    kept += 1
                else:
                    conn.execute("DELETE FROM finding WHERE id=?", (row["id"],))
                    removed += 1
            scan = conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (group["scan"],)).fetchone()
            if scan is not None:
                stats = json.loads(scan["stats_json"] or "{}")
                total = conn.execute("SELECT count(*) FROM finding WHERE program_id=? AND last_seen_scan=?", (group["pid"], group["scan"])).fetchone()[0]
                stats["findings"] = total
                if have_file:
                    stats["takeover"] = {"candidates": len(services), "not_vulnerable": clean, "unreadable": 0}
                stats.setdefault("repairs", []).append({
                    "fix": "takeover_not_vulnerable", "at": utc_now(), "removed": removed, "kept_as_candidate": kept, "downgraded_unverifiable": flagged,
                    "note": ("Trước đây mọi dòng subjack.txt, kể cả “[Not Vulnerable]”, bị lưu thành takeover High. Đã tính lại từ file gốc: "
                             f"{removed} dòng sạch bị bỏ, {kept} ứng viên giữ lại (mức Medium, chưa xác minh)." if have_file else
                             f"Không còn file subjack.txt để kiểm lại: {flagged} mục được hạ xuống info và đánh dấu không đáng tin.")})
                conn.execute("UPDATE scan_run SET stats_json=? WHERE id=?", (json.dumps(stats), group["scan"]))
        done.append({"program": group["slug"], "scan": group["scan"], "removed": removed, "kept": kept, "downgraded": flagged})
    return done


def regenerate_stale_briefs(database, settings, repaired):
    """The brief of the latest completed scan quoted the wrong numbers; rewrite it (best effort, never blocks start-up)."""
    from backend.brief.generator import BriefGenerator
    for slug, scan in {(r["program"], r["scan"]) for r in repaired}:
        with database.connect() as conn:
            latest = conn.execute("SELECT max(s.id) FROM scan_run s JOIN program p ON p.id=s.program_id WHERE p.slug=? AND s.status IN ('done','done_partial')", (slug,)).fetchone()[0]
        if latest == scan:
            try:
                BriefGenerator(settings, database).generate(slug, scan)
            except Exception as exc:   # the data is already corrected; the brief can be regenerated from the Guide tab
                log.warning("brief for %s not regenerated: %s", slug, exc)


def run_repairs(database, settings):
    if not database.path.exists():
        return []
    repaired = repair_takeover(database, settings)
    if repaired:
        regenerate_stale_briefs(database, settings, repaired)
    return repaired
