import sqlite3

import pytest

from backend.db import Database
from backend.migrations import SCHEMA_VERSION


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
        assert [r[0] for r in conn.execute("SELECT version FROM schema_meta")] == [SCHEMA_VERSION]
        assert conn.execute("SELECT count(*) FROM program").fetchone()[0] == 1
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"schema_meta", "program", "scope_rule", "scan_run", "scan_config", "asset", "url", "finding", "diff_event", "schedule", "profile"}
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


def build_v1(path):
    """A database exactly as the P8/v1.1 releases created it (baseline schema, version 1)."""
    from pathlib import Path
    conn = sqlite3.connect(path)
    for statement in (Path(__file__).parents[1] / "schema.sql").read_text(encoding="utf-8").split(";"):
        if statement.strip():
            conn.execute(statement)
    conn.execute("INSERT INTO schema_meta(version) VALUES (1)")
    conn.execute("INSERT INTO program(slug,source,policy_json) VALUES('acme','raw','{}')")
    conn.execute("INSERT INTO scan_run(program_id,depth,status,stats_json) VALUES(1,'light','done','{\"urls\": 3}')")
    conn.execute("INSERT INTO scan_config(scan_run_id,depth,threads) VALUES(1,'light',7)")
    conn.execute("INSERT INTO asset(program_id,host,category,state) VALUES(1,'acme.com','web','active')")
    conn.execute("INSERT INTO url(program_id,asset_id,url,source,first_seen_scan,last_seen_scan) VALUES(1,1,'https://acme.com/a','gau',1,1)")
    conn.commit()
    conn.close()


def test_tc_mig_1_v1_database_is_upgraded_with_backup_and_data_intact(tmp_path):
    path = tmp_path / "data" / "bbasm.db"
    path.parent.mkdir()
    build_v1(path)
    db = Database(path)
    db.migrate()
    with db.connect() as conn:
        assert [r[0] for r in conn.execute("SELECT version FROM schema_meta")] == [SCHEMA_VERSION]
        assert conn.execute("SELECT slug FROM program").fetchone()[0] == "acme"
        row = conn.execute("SELECT url,tags_json,score,verification,status_code FROM url").fetchone()
        assert tuple(row) == ("https://acme.com/a", None, None, None, None)  # old rows get NULL, not defaults
        assert conn.execute("SELECT threads,options_json FROM scan_config").fetchone()[0] == 7
        assert conn.execute("SELECT baseline_scan_id FROM scan_run").fetchone()[0] is None
        conn.execute("INSERT INTO profile(name,config_json) VALUES('mine','{}')")
    backups = list(path.parent.glob("bbasm.db.bak-v1-*"))
    assert len(backups) == 1
    old = sqlite3.connect(backups[0])
    assert old.execute("SELECT version FROM schema_meta").fetchall() == [(1,)]  # backup is the untouched v1
    assert old.execute("SELECT count(*) FROM url").fetchone()[0] == 1
    old.close()


def test_tc_mig_2_second_run_is_a_noop_without_new_backup(tmp_path):
    path = tmp_path / "bbasm.db"
    build_v1(path)
    db = Database(path)
    db.migrate()
    db.migrate()
    assert len(list(tmp_path.glob("bbasm.db.bak-*"))) == 1


def test_tc_mig_3_failed_migration_rolls_back_to_v1(tmp_path, monkeypatch):
    import backend.db as db_module
    path = tmp_path / "bbasm.db"
    build_v1(path)
    monkeypatch.setitem(db_module.MIGRATIONS, 2, ["ALTER TABLE url ADD COLUMN tags_json TEXT", "THIS IS NOT SQL"])
    with pytest.raises(sqlite3.Error):
        Database(path).migrate()
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT version FROM schema_meta").fetchall() == [(1,)]
    assert "tags_json" not in [r[1] for r in conn.execute("PRAGMA table_info(url)")]  # half-applied step undone
    conn.close()


def test_tc_mig_4_future_version_is_refused_not_downgraded(tmp_path):
    path = tmp_path / "bbasm.db"
    conn = sqlite3.connect(path)
    conn.executescript(f"CREATE TABLE schema_meta(version); INSERT INTO schema_meta VALUES({SCHEMA_VERSION + 1})")
    conn.close()
    with pytest.raises(RuntimeError):
        Database(path).migrate()


def test_backups_are_capped_at_three(tmp_path):
    path = tmp_path / "bbasm.db"
    for i in range(5):
        (tmp_path / f"bbasm.db.bak-v1-2026010{i}T000000Z").write_text("x")
    build_v1(path)
    Database(path).migrate()
    assert len(list(tmp_path.glob("bbasm.db.bak-*"))) == 3
