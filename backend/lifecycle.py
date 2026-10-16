"""Program lifecycle: archive (reversible), restore, and permanent delete.

Archiving hides a program and pauses its schedule; nothing else changes, so history, Diff, findings and files stay.
Deleting is only for an archived program with nothing running. The file tree is moved to `targets/.trash` first (a rename is
atomic, a recursive delete is not), then the database rows go (children before parents: asset/url/finding/diff_event have no
foreign keys), then the trash is removed. A crash in between is finished forward at the next start (`finish_pending`)."""
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from backend.db import utc_now
from backend.jobs.scope_resolver import ScopeError
from backend.scope_gate import audit

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,99}$")
CHILD_TABLES = (("diff_event", "program_id"), ("finding", "program_id"), ("url", "program_id"), ("asset", "program_id"))


def _program(conn, slug):
    row = conn.execute("SELECT * FROM program WHERE slug=?", (slug,)).fetchone()
    if row is None:
        raise ScopeError("Program not found", "program_not_found")
    return row


def _active_scans(conn, program_id):
    return conn.execute("SELECT count(*) FROM scan_run WHERE program_id=? AND status IN ('queued','running')", (program_id,)).fetchone()[0]


def archive(database, scheduler, settings, slug):
    with database.connect() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        program = _program(conn, slug)
        if program["archived_at"]:
            return {"slug": slug, "archived_at": program["archived_at"], "schedule_paused": False}
        if _active_scans(conn, program["id"]):
            raise ScopeError("Program đang có scan chạy hoặc chờ chạy; huỷ hoặc đợi xong rồi mới lưu trữ.", "program_busy")
        now = utc_now()
        conn.execute("UPDATE program SET archived_at=? WHERE id=?", (now, program["id"]))
        paused = conn.execute("UPDATE schedule SET enabled=0,paused_by_archive=1 WHERE program_id=? AND enabled=1", (program["id"],)).rowcount > 0
        row = conn.execute("SELECT * FROM schedule WHERE program_id=?", (program["id"],)).fetchone()
    if row is not None:
        scheduler._install(dict(row))      # removes the APScheduler job: nothing keeps running unseen in the background
    audit(settings.BBASM_TARGETS / slug / "audit.jsonl", slug, "allow", "program_archived", schedule_paused=paused)
    return {"slug": slug, "archived_at": now, "schedule_paused": paused}


def restore(database, settings, slug):
    with database.connect() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        program = _program(conn, slug)
        if program["deleting_at"]:
            raise ScopeError("Program đang được xóa.", "program_deleting")
        conn.execute("UPDATE program SET archived_at=NULL WHERE id=?", (program["id"],))
        paused = bool(conn.execute("SELECT 1 FROM schedule WHERE program_id=? AND paused_by_archive=1", (program["id"],)).fetchone())
    audit(settings.BBASM_TARGETS / slug / "audit.jsonl", slug, "allow", "program_restored")
    return {"slug": slug, "archived_at": None, "schedule_was_paused": paused}


def require_active(program):
    """Writes that change how a program behaves are refused while it is archived (restore it first)."""
    if program.get("archived_at"):
        raise ScopeError("Program đã lưu trữ: khôi phục trước khi thay đổi.", "program_archived")


def _target_dir(settings, slug):
    if not SLUG_RE.fullmatch(slug):
        raise ScopeError("Tên program không hợp lệ cho thao tác xóa.", "invalid_slug")
    root = Path(settings.BBASM_TARGETS).resolve()
    path = (root / slug)
    if path.is_symlink():
        raise ScopeError("Thư mục của program là liên kết (symlink); không xóa tự động.", "unsafe_path")
    resolved = path.resolve()
    if resolved == root or not resolved.is_relative_to(root) or resolved.parent != root:
        raise ScopeError("Đường dẫn thư mục program nằm ngoài thư mục targets.", "unsafe_path")
    return path


def _dir_stats(path, limit=200_000):
    files = size = 0
    if path.is_dir():
        for item in path.rglob("*"):
            if item.is_symlink():
                continue
            if item.is_file():
                files += 1
                size += item.stat().st_size
            if files >= limit:
                break
    return {"files": files, "bytes": size}


def preview(database, settings, slug):
    """Exactly what a permanent delete would remove, for the confirmation screen."""
    with database.connect() as conn:
        program = _program(conn, slug)
        pid = program["id"]
        counts = {t: conn.execute(f"SELECT count(*) FROM {t} WHERE {c}=?", (pid,)).fetchone()[0] for t, c in CHILD_TABLES}
        counts["scans"] = conn.execute("SELECT count(*) FROM scan_run WHERE program_id=? AND status!='draft'", (pid,)).fetchone()[0]
        counts["drafts"] = conn.execute("SELECT count(*) FROM scan_run WHERE program_id=? AND status='draft'", (pid,)).fetchone()[0]
        schedule = conn.execute("SELECT enabled FROM schedule WHERE program_id=?", (pid,)).fetchone()
        busy = _active_scans(conn, pid)
    blockers = []
    if not program["archived_at"]:
        blockers.append("Chỉ xóa được program đã lưu trữ: lưu trữ trước.")
    if busy:
        blockers.append("Còn scan đang chạy hoặc chờ chạy.")
    return {"slug": slug, "archived": bool(program["archived_at"]), "counts": counts, "has_schedule": schedule is not None,
            "folder": {"path": str(Path(settings.BBASM_TARGETS) / slug), **_dir_stats(_target_dir(settings, slug))}, "blockers": blockers}


def delete(database, scheduler, runner, settings, slug, confirm_slug):
    """Permanent delete. Returns what was removed. Recoverable at every step (see module docstring)."""
    if confirm_slug != slug:
        raise ScopeError("Nhập đúng tên program để xác nhận xóa vĩnh viễn.", "confirm_mismatch")
    target = _target_dir(settings, slug)
    with database.connect() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        program = _program(conn, slug)
        if not program["archived_at"]:
            raise ScopeError("Chỉ xóa được program đã lưu trữ: lưu trữ trước.", "not_archived")
        if _active_scans(conn, program["id"]):
            raise ScopeError("Còn scan đang chạy hoặc chờ chạy.", "program_busy")
        conn.execute("UPDATE program SET deleting_at=? WHERE id=?", (utc_now(), program["id"]))
        scan_ids = [r[0] for r in conn.execute("SELECT id FROM scan_run WHERE program_id=?", (program["id"],))]
        removed = {"scans": len(scan_ids), **{t: conn.execute(f"SELECT count(*) FROM {t} WHERE {c}=?", (program["id"], )).fetchone()[0] for t, c in CHILD_TABLES}}
        info = {"id": program["id"], "handle": program["handle"], "source": program["source"], "scan_ids": scan_ids}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    kept = _keep_audit(settings, slug, stamp, info, removed)
    trash = None
    try:
        trash = _to_trash(settings, target, slug, stamp)
        _delete_rows(database, scheduler, info["id"])
    except Exception:
        if trash is not None and trash.exists() and not target.exists():
            trash.rename(target)                      # the files go back exactly where they were
        with database.connect() as conn, conn:
            conn.execute("UPDATE program SET deleting_at=NULL WHERE id=?", (info["id"],))
        raise
    _forget_scans(runner, settings, scan_ids)
    if trash is not None:
        shutil.rmtree(trash, ignore_errors=True)       # best effort; a leftover is swept at the next start
    return {"slug": slug, "removed": removed, "audit_copy": str(kept)}


def _keep_audit(settings, slug, stamp, info, removed):
    """The consent/egress trail outlives the program: a copy of its audit file plus a tombstone in the global audit log."""
    archive_dir = Path(settings.BBASM_DATA) / "audit-archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    copy = archive_dir / f"{slug}-{stamp}.jsonl"
    source = Path(settings.BBASM_TARGETS) / slug / "audit.jsonl"
    if source.is_file() and not source.is_symlink():
        shutil.copyfile(source, copy)
    else:
        copy.write_text("", encoding="utf-8")
    audit(Path(settings.BBASM_DATA) / "audit.jsonl", slug, "allow", "program_deleted", handle=info["handle"], source=info["source"],
          scan_ids=info["scan_ids"][:200], removed=removed, audit_copy=copy.name)
    return copy


def _to_trash(settings, target, slug, stamp):
    if not target.exists():
        return None
    trash_root = Path(settings.BBASM_TARGETS) / ".trash"
    trash_root.mkdir(parents=True, exist_ok=True)
    trash = trash_root / f"{slug}-{stamp}"
    target.rename(trash)
    return trash


def _delete_rows(database, scheduler, program_id):
    with database.connect() as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        for table, column in CHILD_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE {column}=?", (program_id,))
        conn.execute("DELETE FROM scan_config WHERE scan_run_id IN (SELECT id FROM scan_run WHERE program_id=?)", (program_id,))
        conn.execute("DELETE FROM scan_run WHERE program_id=?", (program_id,))
        conn.execute("DELETE FROM schedule WHERE program_id=?", (program_id,))
        conn.execute("DELETE FROM scope_rule WHERE program_id=?", (program_id,))
        conn.execute("DELETE FROM program WHERE id=?", (program_id,))
    try:
        scheduler.scheduler.remove_job(f"program-{program_id}")
    except Exception:  # noqa: BLE001  no job was installed
        pass


def _forget_scans(runner, settings, scan_ids):
    """Scan numbers can be handed out again; nothing keyed by the old numbers may survive (logs, caches)."""
    from backend.api import scans as scans_api
    for scan_id in scan_ids:
        runner.logs.forget(scan_id)
        scans_api._REPORT_CACHE.pop(scan_id, None)
        scans_api._REPORT_LOCKS.pop(scan_id, None)


def finish_pending(database, scheduler, runner, settings):
    """At start: complete any delete that was interrupted (forward only: the user already confirmed it) and sweep the trash."""
    if not database.path.exists():
        return 0
    with database.connect() as conn:
        pending = [dict(r) for r in conn.execute("SELECT id,slug FROM program WHERE deleting_at IS NOT NULL")]
    for item in pending:
        try:
            target = _target_dir(settings, item["slug"])
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            _to_trash(settings, target, item["slug"], stamp)
            with database.connect() as conn:
                scan_ids = [r[0] for r in conn.execute("SELECT id FROM scan_run WHERE program_id=?", (item["id"],))]
            _delete_rows(database, scheduler, item["id"])
            _forget_scans(runner, settings, scan_ids)
        except ScopeError:
            continue
    trash_root = Path(settings.BBASM_TARGETS) / ".trash"
    if trash_root.is_dir() and not trash_root.is_symlink():
        for leftover in trash_root.iterdir():
            if not leftover.is_symlink():
                shutil.rmtree(leftover, ignore_errors=True)
    return len(pending)
