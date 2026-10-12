"""Portfolio, filtered surface/findings/diffs and monitoring control."""
import json
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from backend.jobs.scope_resolver import ScopeError, classify, default_config
from backend.models import ScanConfig

router = APIRouter(prefix="/api/programs", tags=["programs"])


def program_row(database, slug):
    if not database.path.exists():
        raise ScopeError("Program not found", "program_not_found")
    with database.connect() as conn:
        row = conn.execute("SELECT * FROM program WHERE slug=?", (slug,)).fetchone()
    if not row:
        raise ScopeError("Program not found", "program_not_found")
    return dict(row)


def decoded(row):
    row = dict(row)
    for column, output in (("tech_json", "tech"), ("rank_reasons_json", "reasons"), ("detail_json", "detail"), ("stats_json", "stats"), ("policy_json", "policy")):
        if column in row:
            row[output] = json.loads(row.pop(column) or ("[]" if output in {"tech", "reasons"} else "{}"))
    return row


@router.get("")
def portfolio(request: Request):
    database = request.app.state.database
    if not database.path.exists():
        return []
    with database.connect() as conn:
        rows = [decoded(r) for r in conn.execute("SELECT * FROM program")]
        for row in rows:
            scan = conn.execute("SELECT * FROM scan_run WHERE program_id=? ORDER BY id DESC LIMIT 1", (row["id"],)).fetchone()
            row["latest_scan"] = decoded(scan) if scan else None
            row["new_count"] = conn.execute("SELECT count(*) FROM diff_event WHERE program_id=? AND scan_run_id=? AND change='new'", (row["id"], scan["id"] if scan else None)).fetchone()[0]
            row["asset_count"] = conn.execute("SELECT count(*) FROM asset WHERE program_id=? AND state='active'", (row["id"],)).fetchone()[0]
    return sorted(rows, key=lambda r: (-r["new_count"], r["slug"]))


@router.get("/{slug}")
def detail(slug: str, request: Request):
    database = request.app.state.database
    program = decoded(program_row(database, slug))
    with database.connect() as conn:
        program["scans"] = [decoded(r) for r in conn.execute("SELECT * FROM scan_run WHERE program_id=? ORDER BY id DESC LIMIT 100", (program["id"],))]
        program["scope"] = [dict(r) for r in conn.execute("SELECT * FROM scope_rule WHERE program_id=?", (program["id"],))]
        schedule = conn.execute("SELECT * FROM schedule WHERE program_id=?", (program["id"],)).fetchone()
        program["schedule"] = dict(schedule) if schedule else None
    return program


@router.get("/{slug}/assets")
def assets(slug: str, request: Request, state: Literal["active", "gone"] | None = None,
           min_rank: float = Query(0, ge=0, le=10), q: str = Query("", max_length=500),
           limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    database = request.app.state.database
    program = program_row(database, slug)
    with database.connect() as conn:
        return [decoded(r) for r in conn.execute("SELECT * FROM asset WHERE program_id=? AND (? IS NULL OR state=?) AND COALESCE(rank_score,0)>=? AND host LIKE ? ORDER BY rank_score DESC,host LIMIT ? OFFSET ?",
                (program["id"], state, state, min_rank, "%" + q + "%", limit, offset))]


@router.get("/{slug}/surface")
def surface(slug: str, request: Request, limit: int = Query(25, ge=1, le=1000)):
    return assets(slug, request, "active", 0, "", limit, 0)


@router.get("/{slug}/diff")
def diff(slug: str, request: Request, scan_id: int | None = None):
    database = request.app.state.database
    program = program_row(database, slug)
    with database.connect() as conn:
        if scan_id is None:
            row = conn.execute("SELECT id FROM scan_run WHERE program_id=? AND status IN ('done','done_partial') ORDER BY id DESC LIMIT 1", (program["id"],)).fetchone()
            scan_id = row[0] if row else None
        return [decoded(r) for r in conn.execute("SELECT * FROM diff_event WHERE program_id=? AND scan_run_id=? ORDER BY id", (program["id"], scan_id))]


@router.get("/{slug}/findings")
def findings(slug: str, request: Request, type: Literal["nuclei", "takeover", "secret", "js-endpoint"] | None = None,
             severity: Literal["info", "low", "medium", "high", "critical"] | None = None,
             limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    database = request.app.state.database
    program = program_row(database, slug)
    with database.connect() as conn:
        return [decoded(r) for r in conn.execute("SELECT * FROM finding WHERE program_id=? AND (? IS NULL OR type=?) AND (? IS NULL OR severity=?) ORDER BY last_seen_scan DESC,id DESC LIMIT ? OFFSET ?",
                (program["id"], type, type, severity, severity, limit, offset))]


class ScheduleRequest(BaseModel):
    interval: Literal["6h", "daily", "weekly"]
    depth: Literal["passive", "light", "strong"]
    enabled: bool = True
    config: ScanConfig | None = None


@router.post("/{slug}/schedule")
async def schedule(slug: str, body: ScheduleRequest, request: Request):
    state = request.app.state
    program = program_row(state.database, slug)
    with state.database.connect() as conn:
        entries = [classify(r["pattern"], r["kind"], r["asset_type"]) for r in conn.execute("SELECT * FROM scope_rule WHERE program_id=?", (program["id"],))]
    config = body.config or default_config(state.settings.model_copy(update={"BBASM_DEFAULT_DEPTH": body.depth}), entries)
    if config.depth != body.depth:
        raise ScopeError("depth must match config.depth")
    return state.scheduler.configure(program["id"], body.interval, config, body.enabled)
