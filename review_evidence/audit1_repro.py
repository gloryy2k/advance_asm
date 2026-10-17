"""AUDIT-1 read-only product QA with synthetic SQLite and loopback-only inputs.

Usage: python -m review_evidence.audit1_repro <path-to-pinned-vendor>
This writes only temporary DB/output under a temporary directory and prints counts.
"""
import json
import sqlite3
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from backend.asm.diff_engine import DiffEngine
from backend.asm import ranking
from backend.asm.ranking import rank_program
from backend.brief.generator import BriefGenerator
from backend.config import Settings
from backend.db import Database
from backend.jobs.ingest import Ingester
from backend.jobs.recon_orch import ReconOrchestrator
from backend.jobs.scope_resolver import ScopeResolver
from backend.models import ResolveRequest
from backend.scope_gate import ScopeGate


def env(root, vendor):
    settings = Settings(_env_file=None, BBASM_BBROOT=vendor, BBASM_DATA=root / "data", BBASM_TARGETS=root / "targets")
    db = Database(settings.BBASM_DATA / "bbasm.db")
    db.migrate()
    return settings, db


def diff_empty_baseline(root, vendor):
    _, db = env(root, vendor)
    with db.connect() as conn, conn:
        program = conn.execute("INSERT INTO program(slug,source) VALUES('fixture','raw')").lastrowid
        first = conn.execute("INSERT INTO scan_run(program_id,depth,status,stats_json) VALUES(?,'light','done',?)",
                             (program, json.dumps({"observations": {"127.0.0.1": {"status_code": 200}}}))).lastrowid
        empty = conn.execute("INSERT INTO scan_run(program_id,depth,status,stats_json) VALUES(?,'light','done',?)",
                             (program, json.dumps({"observations": {}}))).lastrowid
        current = conn.execute("INSERT INTO scan_run(program_id,depth,status,stats_json) VALUES(?,'light','running','{}')", (program,)).lastrowid
        conn.execute("INSERT INTO asset(program_id,host,status_code,tech_json,state,first_seen_scan,last_seen_scan) VALUES(?,'127.0.0.1',200,'[]','gone',?,?)", (program, first, first))
    plan = SimpleNamespace(scan_id=current, program_id=program, config=SimpleNamespace(depth="light"), gate=SimpleNamespace(in_scope=lambda _: True))
    engine = DiffEngine(db)
    engine.capture(plan)
    counts = engine.apply(plan, {"127.0.0.1": {"status_code": 200}}, complete=True)
    with db.connect() as conn:
        baseline = conn.execute("SELECT baseline_scan_id FROM scan_run WHERE id=?", (current,)).fetchone()[0]
    print("DIFF", json.dumps({"first": first, "empty_completed": empty, "current": current, "chosen_baseline": baseline, "counts": counts}))


def nuclei_same_template_two_paths(root, vendor):
    settings, db = env(root, vendor)
    resolver = ScopeResolver(settings, db, Mock())
    result = resolver.resolve(ResolveRequest(input="raw", scope=["127.0.0.1"]))
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    output = plan.commands[0].output
    path = output / "nuclei" / "findings.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for suffix in ("one", "two"):
            stream.write(json.dumps({"template-id": "fixture-template", "matched-at": f"http://127.0.0.1/{suffix}", "info": {"severity": "medium"}}) + "\n")
    stats = Ingester(settings, db).ingest(plan)
    with db.connect() as conn:
        rows = [dict(row) for row in conn.execute("SELECT name,detail_json FROM finding")]
    print("NUCLEI", json.dumps({"input_matches": 2, "stored_findings": len(rows), "stats_findings": stats["findings"], "stored_details": rows}))


def ranking_cost(root, vendor, assets=700, urls=20000):
    _, db = env(root, vendor)
    with db.connect() as conn, conn:
        program = conn.execute("INSERT INTO program(slug,source) VALUES('fixture','raw')").lastrowid
        scan = conn.execute("INSERT INTO scan_run(program_id,depth,status) VALUES(?,'light','done')", (program,)).lastrowid
        for i in range(assets):
            conn.execute("INSERT INTO asset(program_id,host,tech_json,first_seen_scan,last_seen_scan,state) VALUES(?,?,?,?,?,'active')",
                         (program, f"h{i}.localhost", "[]", scan, scan))
        rows = conn.execute("SELECT id FROM asset ORDER BY id").fetchall()
        conn.executemany("INSERT INTO url(program_id,asset_id,url,last_seen_scan) VALUES(?,?,?,?)",
                         ((program, rows[i % assets][0], f"http://h{i % assets}.localhost/p{i}", scan) for i in range(urls)))
        plan = [tuple(row) for row in conn.execute("EXPLAIN QUERY PLAN SELECT url FROM url WHERE asset_id=? AND last_seen_scan=?", (rows[0][0], scan))]
    start = time.monotonic()
    rank_program(db, program, scan)
    no_index = round(time.monotonic() - start, 3)
    with db.connect() as conn, conn:
        conn.execute("CREATE INDEX audit_only_url_asset_seen ON url(asset_id,last_seen_scan)")
        conn.execute("CREATE INDEX audit_only_finding_asset_seen ON finding(asset_id,last_seen_scan)")
        indexed_plan = [tuple(row) for row in conn.execute("EXPLAIN QUERY PLAN SELECT url FROM url WHERE asset_id=? AND last_seen_scan=?", (rows[0][0], scan))]
    start = time.monotonic()
    rank_program(db, program, scan)
    with_index = round(time.monotonic() - start, 3)
    print("RANK", json.dumps({"assets": assets, "urls": urls, "seconds_without_index": no_index, "seconds_with_fixture_index": with_index,
                              "plan_without_index": plan, "plan_with_fixture_index": indexed_plan}))


def repo_scope(root, vendor):
    settings, _ = env(root, vendor)
    gate = ScopeGate(["github.com"], [], root / "audit.jsonl", settings)
    print("SCOPE", json.dumps({"allow_rule": "github.com", "other_repo_allowed": gate.in_scope("repo:https://github.com/other/repo")}))


def policy_refresh(root, vendor):
    settings, db = env(root, vendor)
    resolver = ScopeResolver(settings, db, Mock())
    brief = BriefGenerator(settings, db)
    first = resolver.resolve(ResolveRequest(input="raw", scope=["127.0.0.1"], policy_text="POLICY_VERSION_A"))
    path = brief.ensure_program(first.slug)
    first_file = path.read_text(encoding="utf-8")
    second = resolver.resolve(ResolveRequest(input="raw", scope=["127.0.0.1"], policy_text="POLICY_VERSION_B"))
    brief.ensure_program(second.slug)
    second_file = path.read_text(encoding="utf-8")
    with db.connect() as conn:
        policy = json.loads(conn.execute("SELECT policy_json FROM program WHERE slug=?", (first.slug,)).fetchone()[0])
    print("POLICY", json.dumps({"same_slug": first.slug == second.slug, "db_has_B": "POLICY_VERSION_B" in json.dumps(policy),
                                "file_has_A": "POLICY_VERSION_A" in second_file, "file_has_B": "POLICY_VERSION_B" in second_file,
                                "file_unchanged": first_file == second_file}))


def rank_thread_lock(root, vendor):
    _, db = env(root, vendor)
    with db.connect() as conn, conn:
        program = conn.execute("INSERT INTO program(slug,source) VALUES('fixture','raw')").lastrowid
        scan = conn.execute("INSERT INTO scan_run(program_id,depth,status) VALUES(?,'light','running')", (program,)).lastrowid
        conn.executemany("INSERT INTO asset(program_id,host,tech_json,state,first_seen_scan) VALUES(?,?,'[]','active',?)",
                         ((program, f"h{i}.localhost", scan) for i in range(100)))
    started = threading.Event()
    original = ranking.score_asset

    def slow(*args, **kwargs):
        started.set()
        time.sleep(0.01)  # fixture simulates a rank pass that exceeds its time budget
        return original(*args, **kwargs)

    ranking.score_asset = slow
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            task = pool.submit(rank_program, db, program, scan)
            assert started.wait(2)
            cancelled = task.cancel()  # same inability to stop a running executor thread after wait_for timeout
            with closing(sqlite3.connect(db.path, timeout=0.1)) as other:
                try:
                    other.execute("UPDATE scan_run SET status='done' WHERE id=?", (scan,))
                    blocked = False
                except sqlite3.OperationalError as exc:
                    blocked = "locked" in str(exc)
            task.result(timeout=5)
        with closing(sqlite3.connect(db.path, timeout=1)) as other:
            other.execute("UPDATE scan_run SET status='done' WHERE id=?", (scan,))
            other.commit()
        print("LOCK", json.dumps({"cancelled_running_rank_thread": cancelled, "terminal_write_blocked_while_rank_runs": blocked,
                                  "terminal_write_succeeds_after_rank": True}))
    finally:
        ranking.score_asset = original


if __name__ == "__main__":
    vendor = Path(sys.argv[1]).resolve()
    if not (vendor / "tools" / "scope_checker.py").is_file():
        raise SystemExit("pinned vendor tools not found")
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
        base = Path(folder)
        diff_empty_baseline(base / "diff", vendor)
        nuclei_same_template_two_paths(base / "nuclei", vendor)
        ranking_cost(base / "rank", vendor)
        repo_scope(base / "scope", vendor)
        policy_refresh(base / "policy", vendor)
        rank_thread_lock(base / "lock", vendor)
