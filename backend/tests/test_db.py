import sqlite3

import pytest

from backend.db import Database


def test_schema_wal_migration_is_idempotent(tmp_path):
    db = Database(tmp_path / "data" / "bbasm.db")
    db.migrate()
    with db.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with conn:
            conn.execute("INSERT INTO program(slug,source,policy_json) VALUES('acme','raw','{}')")
            conn.execute("INSERT INTO scan_run(program_id,depth,status) VALUES(1,'light','draft')")
            conn.execute("INSERT INTO scan_config(scan_run_id,depth) VALUES(1,'light')")
            conn.execute("INSERT INTO asset(program_id,host,category) VALUES(1,'acme.com','web')")
    db.migrate()
    with db.connect() as conn:
        assert conn.execute("SELECT version FROM schema_meta").fetchall()[0][0] == 1
        assert conn.execute("SELECT count(*) FROM program").fetchone()[0] == 1
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"schema_meta", "program", "scope_rule", "scan_run", "scan_config", "asset", "url", "finding", "diff_event", "schedule"}
        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {"idx_asset_prog_rank", "idx_diff_prog_scan"} <= indexes
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO scan_config(scan_run_id) VALUES(1)")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO scope_rule(program_id,pattern,kind) VALUES(999,'x.com','in')")


@pytest.mark.parametrize("schema", ["CREATE TABLE legacy(x)", "CREATE TABLE schema_meta(version); INSERT INTO schema_meta VALUES(999)"])
def test_unknown_database_is_not_overwritten(tmp_path, schema):
    db = Database(tmp_path / "bbasm.db")
    with db.connect() as conn:
        conn.executescript(schema)
    with pytest.raises(RuntimeError):
        db.migrate()
    with db.connect() as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='program'").fetchone() is None
