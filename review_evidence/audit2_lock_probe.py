"""AUDIT-2: real rank_program vs real JobRunner._finalize, on disposable SQLite only.

Run inside a Linux container without network. The first experiment deliberately
waits >30 s to measure Database.connect's production busy timeout. The second
uses a shorter timeout only to exercise all four _finalize retry attempts.
"""
import asyncio
import json
import sqlite3
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from backend.asm import ranking
from backend.config import Settings
from backend.db import Database
from backend.jobs.runner import JobRunner


class ShortBusyDatabase(Database):
    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=0.15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()


def setup(root, *, short=False, concurrent=1):
    settings = Settings(_env_file=None, BBASM_DATA=root / "data", BBASM_TARGETS=root / "targets",
                        BBASM_RECON_DISABLED=True, BBASM_UPDATE_TEMPLATES="0",
                        BBASM_MAX_CONCURRENT_SCANS=concurrent)
    db_type = ShortBusyDatabase if short else Database
    db = db_type(settings.BBASM_DATA / "bbasm.db")
    db.migrate()
    scans = []
    with db.connect() as conn, conn:
        for index in range(concurrent):
            program = conn.execute("INSERT INTO program(slug,source) VALUES(?,'raw')", (f"qa-{index}",)).lastrowid
            scan = conn.execute("INSERT INTO scan_run(program_id,depth,status,stats_json) VALUES(?,'strong','running','{}')", (program,)).lastrowid
            conn.execute("INSERT INTO asset(program_id,host,tech_json,state,first_seen_scan) VALUES(?,?,'[]','active',?)",
                         (program, f"h{index}.localhost", scan))
            scans.append((program, scan))
    return settings, db, scans


def experiment(root, *, sleep_seconds, short=False, concurrent=1):
    settings, db, scans = setup(root, short=short, concurrent=concurrent)
    runner = JobRunner(settings, db)
    began = threading.Event()
    original_score = ranking.score_asset
    attempts = []
    original_transition = runner._transition

    def slow_score(*args, **kwargs):
        began.set()
        time.sleep(sleep_seconds)
        return original_score(*args, **kwargs)

    def measured_transition(scan_id, status, error=None, stats=None):
        started = time.monotonic()
        try:
            value = original_transition(scan_id, status, error, stats)
            attempts.append({"scan": scan_id, "outcome": "ok", "elapsed_s": round(time.monotonic() - started, 2)})
            return value
        except Exception as exc:
            attempts.append({"scan": scan_id, "outcome": type(exc).__name__, "elapsed_s": round(time.monotonic() - started, 2)})
            raise

    ranking.score_asset = slow_score
    runner._transition = measured_transition
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            rank = pool.submit(ranking.rank_program, db, scans[0][0], scans[0][1])
            assert began.wait(5), "rank did not enter its scoring loop"

            async def finish_all():
                return await asyncio.gather(*(runner._finalize(scan, "done", None, {}) for _, scan in scans),
                                            return_exceptions=True)

            started = time.monotonic()
            results = asyncio.run(finish_all())
            used = round(time.monotonic() - started, 2)
            rank.result(timeout=sleep_seconds + 5)
        with db.connect() as conn:
            statuses = [conn.execute("SELECT status FROM scan_run WHERE id=?", (scan,)).fetchone()[0] for _, scan in scans]
        return {"configured_busy_timeout_s": 0.15 if short else 30,
                "max_concurrent_scans": concurrent, "rank_hold_s": sleep_seconds,
                "finalize_elapsed_s": used, "attempts": attempts, "statuses": statuses,
                "finalize_errors": [type(r).__name__ for r in results if isinstance(r, BaseException)]}
    finally:
        ranking.score_asset = original_score
        runner.executor.shutdown(wait=True, cancel_futures=True)
        runner.control_executor.shutdown(wait=True, cancel_futures=True)


def worker_fallback_experiment(root):
    settings, db, scans = setup(root, short=True, concurrent=2)
    runner = JobRunner(settings, db)
    began = threading.Event()
    original_score = ranking.score_asset

    def slow_score(*args, **kwargs):
        began.set()
        time.sleep(8)
        return original_score(*args, **kwargs)

    async def finalization_only(scan_id):
        await runner._finalize(scan_id, "failed", "qa fixture", {})

    ranking.score_asset = slow_score
    runner._execute = finalization_only
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            rank = pool.submit(ranking.rank_program, db, scans[0][0], scans[0][1])
            assert began.wait(5)

            async def run_workers():
                runner.submitted.update(scan for _, scan in scans)
                tasks = [asyncio.create_task(runner._worker()) for _ in scans]
                for _, scan in scans:
                    await runner.queue.put(scan)
                await asyncio.wait_for(runner.queue.join(), 8)
                return [type(t.exception()).__name__ if t.done() and t.exception() else None for t in tasks]

            worker_errors = asyncio.run(run_workers())
            rank.result(timeout=12)
        with db.connect() as conn:
            statuses = [conn.execute("SELECT status FROM scan_run WHERE id=?", (scan,)).fetchone()[0] for _, scan in scans]
        return {"worker_errors": worker_errors, "statuses": statuses}
    finally:
        ranking.score_asset = original_score
        runner.executor.shutdown(wait=True, cancel_futures=True)
        runner.control_executor.shutdown(wait=True, cancel_futures=True)


with tempfile.TemporaryDirectory() as folder:
    base = Path(folder)
    if "--worker-only" in sys.argv:
        print("LOCK_SCALED_WORKER_FALLBACK", json.dumps(worker_fallback_experiment(base / "worker")))
    else:
        print("LOCK_REAL_30S", json.dumps(experiment(base / "real", sleep_seconds=35)))
        print("LOCK_SCALED_TWO_SCANS", json.dumps(experiment(base / "scaled", sleep_seconds=8, short=True, concurrent=2)))
