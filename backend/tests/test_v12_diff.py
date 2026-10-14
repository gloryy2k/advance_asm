"""R4: Diff must compare against the last *completed* scan's evidence, whatever happened in between."""
import json

from backend.asm.diff_engine import DiffEngine
from backend.jobs.ingest import Ingester
from backend.jobs.recon_orch import ReconOrchestrator
from backend.models import ResolveRequest
from backend.tests.p2_helpers import environment, write_output

LIVE = {"subdomains/all.txt": "vuihoc.vn\n", "live/urls.txt": "https://vuihoc.vn\n",
        "live/httpx_full.txt": "https://vuihoc.vn [200] [100] [Title] [nginx,PHP]\n"}
PASSIVE = {"subdomains/all.txt": "vuihoc.vn\n", "urls/all.txt": "https://vuihoc.vn/a\nhttps://vuihoc.vn/b\n"}


def finish(settings, db, scan_id, files, status="done"):
    plan = ReconOrchestrator(settings, db).build(scan_id)
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='running' WHERE id=?", (scan_id,))
    engine = DiffEngine(db)
    engine.capture(plan)
    for relative, text in files.items():
        write_output(plan.commands[0].output, relative, text)
    stats = Ingester(settings, db).ingest(plan)
    stats["diff"] = engine.apply(plan, stats["observations"], complete=True)
    with db.connect() as conn, conn:
        old = json.loads(conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (scan_id,)).fetchone()[0])
        conn.execute("UPDATE scan_run SET status=?,stats_json=? WHERE id=?", (status, json.dumps({**old, **stats}), scan_id))
    return stats["diff"]


def test_tc_df_5_passive_then_light_shows_changed_even_when_cancelled_scans_polluted_assets(settings):
    db, resolver, first = environment(settings, ["vuihoc.vn"])
    assert finish(settings, db, first.scan_id, PASSIVE) == {"new": 1, "changed": 0, "gone": 0}
    # Two cancelled Light scans in between; one of them leaves the asset row looking already probed.
    for _ in range(2):
        cancelled = resolver.resolve(ResolveRequest(input="raw", scope=["vuihoc.vn"]))
        with db.connect() as conn, conn:
            conn.execute("UPDATE scan_run SET status='cancelled' WHERE id=?", (cancelled.scan_id,))
    with db.connect() as conn, conn:
        conn.execute("UPDATE asset SET status_code=200, tech_json='[\"nginx\",\"PHP\"]'")  # the contamination
    light = resolver.resolve(ResolveRequest(input="raw", scope=["vuihoc.vn"]))
    assert finish(settings, db, light.scan_id, LIVE) == {"new": 0, "changed": 1, "gone": 0}
    with db.connect() as conn:
        event = conn.execute("SELECT * FROM diff_event WHERE scan_run_id=?", (light.scan_id,)).fetchone()
        assert json.loads(event["detail_json"])["status_code"] == {"before": None, "after": 200}
        row = conn.execute("SELECT baseline_scan_id FROM scan_run WHERE id=?", (light.scan_id,)).fetchone()
        assert row[0] == first.scan_id  # the comparison is named, so the UI can say "so với scan #N"
        stats = json.loads(conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (light.scan_id,)).fetchone()[0])
        assert stats["diff_compared_hosts"] == 1


def test_baseline_skips_failed_and_cancelled_and_uses_latest_completed(settings):
    db, resolver, a = environment(settings, ["vuihoc.vn"])
    finish(settings, db, a.scan_id, PASSIVE)
    b = resolver.resolve(ResolveRequest(input="raw", scope=["vuihoc.vn"]))
    finish(settings, db, b.scan_id, LIVE, status="failed")  # ingested but not trustworthy as a baseline
    c = resolver.resolve(ResolveRequest(input="raw", scope=["vuihoc.vn"]))
    diff = finish(settings, db, c.scan_id, {**LIVE, "live/httpx_full.txt": "https://vuihoc.vn [403] [1] [T] [nginx]\n"})
    assert diff["changed"] == 1
    with db.connect() as conn:
        assert conn.execute("SELECT baseline_scan_id FROM scan_run WHERE id=?", (c.scan_id,)).fetchone()[0] == a.scan_id
        detail = json.loads(conn.execute("SELECT detail_json FROM diff_event WHERE scan_run_id=? AND change='changed'", (c.scan_id,)).fetchone()[0])
        assert detail["status_code"] == {"before": None, "after": 403}


def test_two_identical_completed_scans_have_no_diff_and_gone_still_detected(settings):
    db, resolver, a = environment(settings, ["*.example.com"])
    finish(settings, db, a.scan_id, {"subdomains/all.txt": "a.example.com\nb.example.com\n"})
    b = resolver.resolve(ResolveRequest(input="raw", scope=["*.example.com"]))
    diff = finish(settings, db, b.scan_id, {"subdomains/all.txt": "a.example.com\n"})
    assert diff == {"new": 0, "changed": 0, "gone": 1}
