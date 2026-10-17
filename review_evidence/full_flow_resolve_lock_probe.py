"""AUDIT full-flow: a slow fake H1 provider holds ScopeResolver's SQLite write lock."""
import json
import sqlite3
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from backend.config import Settings
from backend.db import Database
from backend.jobs.scope_resolver import ScopeResolver, classify
from backend.models import ResolveRequest


class ShortBusyDatabase(Database):
    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=0.15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()


class DelayedProvider:
    def __init__(self):
        self.began = threading.Event()
        self.release = threading.Event()

    def resolve(self, handle, audit_path):
        self.began.set()
        if not self.release.wait(5):
            raise TimeoutError("fixture provider not released")
        return [classify("127.0.0.1")], {"policy_source": "public_page", "policy_text": "fixture"}, []


with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    settings = Settings(_env_file=None, BBASM_DATA=root / "data", BBASM_TARGETS=root / "targets",
                        BBASM_BBROOT=Path("vendor/claude-bug-bounty").resolve(),
                        BBASM_RECON_DISABLED=True, BBASM_UPDATE_TEMPLATES="0")
    db = ShortBusyDatabase(settings.BBASM_DATA / "bbasm.db")
    db.migrate()
    provider = DelayedProvider()
    resolver = ScopeResolver(settings, db, provider)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(resolver.resolve, ResolveRequest(input="h1:qa-fixture"))
        assert provider.began.wait(5)
        began = time.monotonic()
        outcome = "ok"
        try:
            with db.connect() as conn, conn:
                conn.execute("INSERT INTO program(slug,source) VALUES('qa-other','raw')")
        except Exception as exc:
            outcome = type(exc).__name__
        elapsed = round(time.monotonic() - began, 2)
        provider.release.set()
        result = future.result(timeout=5)
    print("H1_RESOLVE_WRITE_LOCK", json.dumps({"provider": "fake", "other_write": outcome,
                                              "other_write_elapsed_s": elapsed, "resolve_slug": result.slug}))
