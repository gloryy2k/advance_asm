"""arc-bbp Strong #65 (F1): 124 `[Not Vulnerable]` lines of subjack.txt were stored as 128 High takeovers."""
import json

from fastapi.testclient import TestClient

from backend.asm.monitors import Monitors
from backend.asm.takeover import parse_subjack
from backend.jobs.ingest import Ingester
from backend.jobs.recon_orch import ReconOrchestrator
from backend.main import create_app
from backend.repair import run_repairs
from backend.tests.p2_helpers import environment, write_output
from backend.tests.test_v152_lifecycle import program, settings_for

SUBJACK = ("[Not Vulnerable] cpcalendars.arc.io\n[GEMFURY] pkg.arc.io\n[Not Vulnerable] www.arc.io\n"
           "[Not Vulnerable] api.arc.io\n[Vulnerable] old.arc.io\nsubjack finished\n\n[not vulnerable] x.arc.io\n")


def test_parser_keeps_only_real_candidates():
    candidates, clean, unreadable = parse_subjack(SUBJACK.splitlines())
    assert candidates == [("pkg.arc.io", "GEMFURY"), ("old.arc.io", "VULNERABLE")]
    assert clean == 4 and unreadable == 1                                   # the free-text line is neither guessed at nor counted as clean


def test_scan_ingest_stores_only_candidates_as_unverified_and_counts_the_rest(settings):
    db, _, result = environment(settings, ["*.example.com"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    write_output(plan.commands[0].output, "subdomains/all.txt", "api.example.com\nwww.example.com\npkg.example.com\n")
    Ingester(settings, db).ingest(plan)
    write_output(plan.root, "monitors/takeover/subjack.txt",
                 "[Not Vulnerable] api.example.com\n[Not Vulnerable] www.example.com\n[GEMFURY] pkg.example.com\n")
    assert Monitors(settings, db).ingest(plan) == 1
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT name,severity,detail_json FROM finding WHERE type='takeover'")]
    assert [(r["name"], r["severity"]) for r in rows] == [("subjack:GEMFURY", "medium")]       # a candidate is not a confirmed High
    assert json.loads(rows[0]["detail_json"])["verified"] is False
    assert plan.takeover_summary == {"candidates": 1, "not_vulnerable": 2, "unreadable": 0}


def seed_legacy(client, files):
    """What v1.5.5 stored for scan #65: one `subjack.txt:candidate` High per line of subjack.txt."""
    scan = program(client, "arc")
    db = client.app.state.database
    with db.connect() as conn, conn:
        pid = conn.execute("SELECT id FROM program WHERE slug='arc'").fetchone()[0]
        for host in ("cpcalendars", "pkg", "www"):
            conn.execute("INSERT INTO asset(program_id,host,state,category,first_seen_scan,last_seen_scan) VALUES(?,?,?,?,?,?)", (pid, f"{host}.arc.io", "active", "web", scan, scan))
            aid = conn.execute("SELECT id FROM asset WHERE host=?", (f"{host}.arc.io",)).fetchone()[0]
            conn.execute("INSERT INTO finding(program_id,asset_id,type,severity,name,detail_json,first_seen_scan,last_seen_scan) VALUES(?,?,?,?,?,?,?,?)",
                         (pid, aid, "takeover", "high", "subjack.txt:candidate", json.dumps({"source": "subjack.txt", "candidate": True}), scan, scan))
        conn.execute("UPDATE scan_run SET stats_json=? WHERE id=?", (json.dumps({"findings": 3, "observed": 3}), scan))
    if files:
        path = client.app.state.settings.BBASM_TARGETS / "arc" / "recon" / "scans" / str(scan) / "monitors" / "takeover" / "subjack.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[Not Vulnerable] cpcalendars.arc.io\n[GEMFURY] pkg.arc.io\n[Not Vulnerable] www.arc.io\n", encoding="utf-8")
    return scan


def test_stored_results_from_the_old_parser_are_corrected_from_the_scans_own_file(settings):
    settings = settings_for(settings)
    with TestClient(create_app(settings)) as client:
        scan = seed_legacy(client, files=True)
        findings = client.get("/api/programs/arc/findings?type=takeover").json()
        assert len(findings) == 3 and {f["severity"] for f in findings} == {"high"}                  # the state #65 is in today
        done = run_repairs(client.app.state.database, settings)
        assert done == [{"program": "arc", "scan": scan, "removed": 2, "kept": 1, "downgraded": 0}]
        after = client.get("/api/programs/arc/findings?type=takeover").json()
        assert [(f["name"], f["severity"]) for f in after] == [("subjack:GEMFURY", "medium")]
        stats = json.loads(client.get(f"/api/scans/{scan}").json()["stats_json"])
        assert stats["findings"] == 1 and stats["takeover"] == {"candidates": 1, "not_vulnerable": 2, "unreadable": 0}
        assert stats["repairs"][0]["fix"] == "takeover_not_vulnerable" and stats["repairs"][0]["removed"] == 2
        assert run_repairs(client.app.state.database, settings) == []                             # idempotent
        assert list(settings.BBASM_DATA.glob("bbasm.db.pre-repair-takeover-*"))                  # a copy was taken first
        summary = client.get("/api/programs/arc/summary").json()
        assert summary["data_notes"][0]["fix"] == "takeover_not_vulnerable"                       # the UI can say the numbers were recalculated


def test_without_the_original_file_nothing_stays_high(settings):
    settings = settings_for(settings)
    with TestClient(create_app(settings)) as client:
        seed_legacy(client, files=False)
        run_repairs(client.app.state.database, settings)
        items = client.get("/api/programs/arc/findings?type=takeover").json()
        assert len(items) == 3 and {f["severity"] for f in items} == {"info"}
        assert all(f["detail"]["legacy_unreliable"] for f in items)
