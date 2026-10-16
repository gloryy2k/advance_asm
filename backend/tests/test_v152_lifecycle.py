"""Archive / restore / permanent delete of a program, and bulk draft cleanup."""
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from backend.main import create_app


def program(client, name="acme", scope=("a.example.com",), launch=True):
    made = client.post("/api/scope/resolve", json={"input": "raw", "scope": list(scope), "name": name}).json()
    scan = made["scan_id"]
    if launch:
        cfg = client.get(f"/api/scans/{scan}/config").json() | {"depth": "passive", "scan_timeout": 300, "skip_nuclei": True, "skip_active_crawl": True}
        client.put(f"/api/scans/{scan}/config", json=cfg)
        assert client.post(f"/api/scans/{scan}/launch", json={}).status_code == 200
        # The worker thread finishes (fails: no tools here) on its own; wait for it, or it overwrites the status set below.
        for _ in range(200):
            with client.app.state.database.connect() as conn:
                if conn.execute("SELECT status FROM scan_run WHERE id=?", (scan,)).fetchone()[0] not in ("queued", "running"):
                    break
            time.sleep(0.05)
        with client.app.state.database.connect() as conn, conn:
            conn.execute("UPDATE scan_run SET status='done' WHERE id=?", (scan,))
    return scan


def seed(client, name="acme"):
    db = client.app.state.database
    with db.connect() as conn, conn:
        pid = conn.execute("SELECT id FROM program WHERE slug=?", (name,)).fetchone()[0]
        sid = conn.execute("SELECT max(id) FROM scan_run WHERE program_id=?", (pid,)).fetchone()[0]
        conn.execute("INSERT INTO asset(program_id,host,state,category,first_seen_scan,last_seen_scan) VALUES(?,?,?,?,?,?)", (pid, "a.example.com", "active", "web", sid, sid))
        conn.execute("INSERT INTO url(program_id,url,source,first_seen_scan,last_seen_scan) VALUES(?,?,?,?,?)", (pid, "https://a.example.com/x", "gau", sid, sid))
        conn.execute("INSERT INTO finding(program_id,type,severity,name,first_seen_scan,last_seen_scan) VALUES(?,?,?,?,?,?)", (pid, "nuclei", "low", "f", sid, sid))
        conn.execute("INSERT INTO diff_event(program_id,scan_run_id,entity,entity_ref,change,created_at) VALUES(?,?,?,?,?,?)", (pid, sid, "asset", "a.example.com", "new", "2026-01-01"))
    return pid, sid


def counts(db):
    with db.connect() as conn:
        return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("program", "scan_run", "scan_config", "scope_rule", "schedule", "asset", "url", "finding", "diff_event")}


def settings_for(settings):
    from backend.config import PROJECT_ROOT
    return settings.model_copy(update={"BBASM_RECON_DISABLED": True, "BBASM_BBROOT": PROJECT_ROOT / "vendor/claude-bug-bounty"})


def test_archive_hides_pauses_the_schedule_and_keeps_everything_then_restore(settings):
    with TestClient(create_app(settings_for(settings))) as client:
        program(client)
        pid, _ = seed(client)
        client.post("/api/programs/acme/schedule", json={"interval": "daily", "depth": "passive", "enabled": True})
        assert client.app.state.scheduler.scheduler.get_job(f"program-{pid}") is not None
        before = counts(client.app.state.database)
        r = client.post("/api/programs/acme/archive").json()
        assert r["schedule_paused"] is True and r["archived_at"]
        assert counts(client.app.state.database) == before                           # not one row changed
        assert client.app.state.scheduler.scheduler.get_job(f"program-{pid}") is None
        assert [p["slug"] for p in client.get("/api/programs").json()] == []
        assert [p["slug"] for p in client.get("/api/programs?archived=only").json()] == ["acme"]
        assert [p["slug"] for p in client.get("/api/programs?archived=include").json()] == ["acme"]
        summary = client.get("/api/programs/acme/summary").json()
        assert summary["archived_at"] and summary["schedule"]["enabled"] == 0 and summary["schedule"]["paused_by_archive"] == 1
        assert client.get("/api/programs/acme/urls").status_code == 200              # history is still readable
        for blocked in (client.put("/api/programs/acme/request-headers", json={"headers": []}),
                        client.post("/api/programs/acme/schedule", json={"interval": "daily", "depth": "passive", "enabled": True}),
                        client.put("/api/programs/acme/default-profile", json={"profile_id": None})):
            assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "program_archived"
        back = client.post("/api/programs/acme/restore").json()
        assert back["archived_at"] is None and back["schedule_was_paused"] is True
        assert [p["slug"] for p in client.get("/api/programs").json()] == ["acme"]
        assert client.get("/api/programs/acme/summary").json()["schedule"]["enabled"] == 0   # never re-enabled by itself


def test_archive_is_refused_while_a_scan_runs_and_dispatch_skips_archived(settings):
    with TestClient(create_app(settings_for(settings))) as client:
        program(client)
        db = client.app.state.database
        with db.connect() as conn, conn:
            conn.execute("INSERT INTO scan_run(program_id,depth,status,trigger,stats_json) VALUES(1,'passive','running','manual','{}')")
        busy = client.post("/api/programs/acme/archive")
        assert busy.status_code == 422 and busy.json()["error"]["code"] == "program_busy"
        with db.connect() as conn, conn:
            conn.execute("UPDATE scan_run SET status='done' WHERE status='running'")
        client.post("/api/programs/acme/schedule", json={"interval": "daily", "depth": "passive", "enabled": True})
        client.post("/api/programs/acme/archive")
        scheduler = client.app.state.scheduler
        scheduler.runner.adopt_queued = AsyncMock()
        with db.connect() as conn, conn:
            conn.execute("UPDATE schedule SET enabled=1,next_run_at=?", ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),))
        assert asyncio.new_event_loop().run_until_complete(scheduler.dispatch(1)) is None
        scheduler.runner.adopt_queued.assert_not_awaited()


def test_launching_a_draft_of_an_archived_program_restores_it(settings):
    with TestClient(create_app(settings_for(settings))) as client:
        program(client)
        client.post("/api/programs/acme/archive")
        draft = client.post("/api/programs/acme/rescan").json()["scan_id"]
        assert client.get(f"/api/scans/{draft}/review").json()["archived"] is True
        cfg = client.get(f"/api/scans/{draft}/config").json() | {"depth": "passive", "scan_timeout": 300, "skip_nuclei": True, "skip_active_crawl": True}
        client.put(f"/api/scans/{draft}/config", json=cfg)
        assert client.post(f"/api/scans/{draft}/launch", json={}).status_code == 200
        assert [p["slug"] for p in client.get("/api/programs").json()] == ["acme"]


def test_permanent_delete_needs_archive_name_and_removes_exactly_one_program(settings):
    s = settings_for(settings)
    with TestClient(create_app(s)) as client:
        program(client, "acme")
        program(client, "other", scope=("b.example.com",))
        pid, sid = seed(client, "acme")
        seed(client, "other")
        db = client.app.state.database
        folder = Path(s.BBASM_TARGETS) / "acme"
        (folder / "recon").mkdir(parents=True, exist_ok=True)
        (folder / "recon" / "big.txt").write_text("x" * 1000)
        client.app.state.runner.logs.events[sid] = None            # a journal for a scan number that will be freed
        (s.BBASM_DATA / "logs").mkdir(parents=True, exist_ok=True)
        (s.BBASM_DATA / "logs" / f"{sid}.jsonl").write_text("{}\n")
        client.app.state.runner.logs.events.pop(sid)
        other_before = None
        with db.connect() as conn:
            other_before = {t: conn.execute(f"SELECT count(*) FROM {t} WHERE program_id=2").fetchone()[0] for t in ("asset", "url", "finding", "diff_event", "scan_run")}
        # refused: not archived, wrong confirmation
        r = client.request("DELETE", "/api/programs/acme", json={"confirm_slug": "acme"})
        assert r.status_code == 422 and r.json()["error"]["code"] == "not_archived"
        client.post("/api/programs/acme/archive")
        preview = client.get("/api/programs/acme/delete-preview").json()
        assert preview["counts"]["url"] == 1 and preview["counts"]["finding"] == 1 and preview["folder"]["files"] >= 1 and preview["blockers"] == []
        r = client.request("DELETE", "/api/programs/acme", json={"confirm_slug": "nope"})
        assert r.status_code == 422 and r.json()["error"]["code"] == "confirm_mismatch"
        assert folder.exists()
        done = client.request("DELETE", "/api/programs/acme", json={"confirm_slug": "acme"})
        assert done.status_code == 200, done.text
        # gone: rows, files, logs; the other program is untouched; the audit trail survives
        assert not folder.exists() and not (Path(s.BBASM_TARGETS) / ".trash").exists() or not list((Path(s.BBASM_TARGETS) / ".trash").iterdir())
        assert not (s.BBASM_DATA / "logs" / f"{sid}.jsonl").exists()
        with db.connect() as conn:
            assert conn.execute("SELECT count(*) FROM program WHERE slug='acme'").fetchone()[0] == 0
            for table in ("asset", "url", "finding", "diff_event", "scan_run", "scope_rule", "schedule"):
                assert conn.execute(f"SELECT count(*) FROM {table} WHERE program_id=?", (pid,)).fetchone()[0] == 0, table
            assert conn.execute("SELECT count(*) FROM scan_config WHERE scan_run_id=?", (sid,)).fetchone()[0] == 0
            assert {t: conn.execute(f"SELECT count(*) FROM {t} WHERE program_id=2").fetchone()[0] for t in ("asset", "url", "finding", "diff_event", "scan_run")} == other_before
        tomb = [json.loads(line) for line in (s.BBASM_DATA / "audit.jsonl").read_text().splitlines() if "program_deleted" in line]
        assert tomb and tomb[0]["host"] == "acme" and tomb[0]["removed"]["url"] == 1
        assert list((s.BBASM_DATA / "audit-archive").glob("acme-*.jsonl"))
        assert client.get("/api/programs/acme/summary").status_code == 422


def test_a_database_failure_puts_the_files_back_and_an_interrupted_delete_is_finished(settings, monkeypatch):
    import backend.lifecycle as lifecycle
    s = settings_for(settings)
    with TestClient(create_app(s)) as client:
        program(client)
        seed(client)
        client.post("/api/programs/acme/archive")
        folder = Path(s.BBASM_TARGETS) / "acme"
        (folder / "keep.txt").write_text("precious")
        real = lifecycle._delete_rows
        monkeypatch.setattr(lifecycle, "_delete_rows", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))
        try:
            client.request("DELETE", "/api/programs/acme", json={"confirm_slug": "acme"})
        except RuntimeError:
            pass
        assert (folder / "keep.txt").read_text() == "precious"                           # rolled back: files are where they were
        with client.app.state.database.connect() as conn:
            row = conn.execute("SELECT deleting_at FROM program WHERE slug='acme'").fetchone()
        assert row is not None and row["deleting_at"] is None
        # a crash after the rename but before the rows go: the next start finishes it
        with client.app.state.database.connect() as conn, conn:
            conn.execute("UPDATE program SET deleting_at='2026-01-01T00:00:00.000Z'")
        monkeypatch.setattr(lifecycle, "_delete_rows", real)
        assert lifecycle.finish_pending(client.app.state.database, client.app.state.scheduler, client.app.state.runner, s) == 1
        with client.app.state.database.connect() as conn:
            assert conn.execute("SELECT count(*) FROM program").fetchone()[0] == 0
        assert not folder.exists()


def test_delete_refuses_unsafe_names_and_links(settings, tmp_path):
    import pytest
    from backend.lifecycle import _target_dir
    from backend.jobs.scope_resolver import ScopeError
    s = settings_for(settings)
    s.BBASM_TARGETS.mkdir(parents=True, exist_ok=True)
    for bad in ("..", "a/b", ".hidden", "UPPER", "x" * 200, ""):
        with pytest.raises(ScopeError):
            _target_dir(s, bad)
    (tmp_path / "elsewhere").mkdir()
    (s.BBASM_TARGETS / "linked").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(ScopeError) as err:
        _target_dir(s, "linked")
    assert err.value.code == "unsafe_path"


def test_bulk_draft_delete_rechecks_each_draft(settings):
    with TestClient(create_app(settings_for(settings))) as client:
        a = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["a.example.com"], "name": "one"}).json()["scan_id"]
        b = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["b.example.com"], "name": "two"}).json()["scan_id"]
        c = program(client, "three", scope=("c.example.com",))      # launched: not a draft any more
        with client.app.state.database.connect() as conn:
            assert conn.execute("SELECT count(*) FROM program").fetchone()[0] == 3
        r = client.post("/api/drafts/delete", json={"ids": [a, b, c, 9999]}).json()
        assert sorted(r["deleted"]) == sorted([a, b]) and {(s["id"], s["reason"]) for s in r["skipped"]} == {(c, "not_draft"), (9999, "not_found")}
        with client.app.state.database.connect() as conn:
            assert [x[0] for x in conn.execute("SELECT slug FROM program")] == ["three"]    # abandoned programs of deleted drafts went too
            assert conn.execute("SELECT status FROM scan_run WHERE id=?", (c,)).fetchone()[0] == "done"
        assert client.post("/api/drafts/delete", json={"ids": []}).status_code == 422
