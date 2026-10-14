"""Portfolio, filtered surface/findings/diffs and monitoring control."""
import json
from typing import Literal

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import PlainTextResponse
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
def portfolio(request: Request, include_drafts: bool = False):
    database = request.app.state.database
    if not database.path.exists():
        return []
    result = []
    with database.connect() as conn:
        for program in conn.execute("SELECT * FROM program"):
            row = decoded(program)
            scan = conn.execute("SELECT * FROM scan_run WHERE program_id=? AND status!='draft' ORDER BY id DESC LIMIT 1", (row["id"],)).fetchone()
            row["draft_count"] = conn.execute("SELECT count(*) FROM scan_run WHERE program_id=? AND status='draft'", (row["id"],)).fetchone()[0]
            if scan is None and not include_drafts:
                continue  # resolved but never launched: listed under /api/drafts, not as a program
            row["latest_scan"] = decoded(scan) if scan else None
            row["new_count"] = conn.execute("SELECT count(*) FROM diff_event WHERE program_id=? AND scan_run_id=? AND change='new'", (row["id"], scan["id"] if scan else None)).fetchone()[0]
            row["asset_count"] = conn.execute("SELECT count(*) FROM asset WHERE program_id=? AND state='active'", (row["id"],)).fetchone()[0]
            row["finding_count"] = conn.execute("SELECT count(*) FROM finding WHERE program_id=?", (row["id"],)).fetchone()[0]
            row["monitoring"] = bool(conn.execute("SELECT 1 FROM schedule WHERE program_id=? AND enabled=1", (row["id"],)).fetchone())
            result.append(row)
    return sorted(result, key=lambda r: (-r["new_count"], r["slug"]))


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
def assets(slug: str, request: Request, response: Response = None, state: Literal["active", "gone"] | None = None,
           min_rank: float = Query(0, ge=0, le=10), q: str = Query("", max_length=500),
           category: str | None = Query(None, max_length=20),
           limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    database = request.app.state.database
    program = program_row(database, slug)
    where = "program_id=? AND (? IS NULL OR state=?) AND COALESCE(rank_score,0)>=? AND host LIKE ? ESCAPE '\\' AND (? IS NULL OR category=?)"
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    args = (program["id"], state, state, min_rank, like, category, category)
    with database.connect() as conn:
        if response is not None:
            response.headers["X-Total-Count"] = str(conn.execute("SELECT count(*) FROM asset WHERE " + where, args).fetchone()[0])
        return [decoded(r) for r in conn.execute("SELECT * FROM asset WHERE " + where + " ORDER BY rank_score DESC,host LIMIT ? OFFSET ?", (*args, limit, offset))]


@router.get("/{slug}/surface")
def surface(slug: str, request: Request, limit: int = Query(25, ge=1, le=1000)):
    return assets(slug, request, None, "active", 0, "", None, limit, 0)


@router.get("/{slug}/diff")
def diff(slug: str, request: Request, response: Response, scan_id: int | None = None,
         change: Literal["new", "changed", "gone"] | None = None,
         limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    database = request.app.state.database
    program = program_row(database, slug)
    with database.connect() as conn:
        if scan_id is None:
            row = conn.execute("SELECT id FROM scan_run WHERE program_id=? AND status IN ('done','done_partial') ORDER BY id DESC LIMIT 1", (program["id"],)).fetchone()
            scan_id = row[0] if row else None
        where, args = "program_id=? AND scan_run_id=? AND (? IS NULL OR change=?)", (program["id"], scan_id, change, change)
        response.headers["X-Total-Count"] = str(conn.execute("SELECT count(*) FROM diff_event WHERE " + where, args).fetchone()[0])
        return [decoded(r) for r in conn.execute("SELECT * FROM diff_event WHERE " + where + " ORDER BY id LIMIT ? OFFSET ?", (*args, limit, offset))]


@router.get("/{slug}/findings")
def findings(slug: str, request: Request, response: Response, type: Literal["nuclei", "takeover", "secret", "js-endpoint"] | None = None,
             severity: Literal["info", "low", "medium", "high", "critical"] | None = None,
             limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    database = request.app.state.database
    program = program_row(database, slug)
    where = "f.program_id=? AND (? IS NULL OR f.type=?) AND (? IS NULL OR f.severity=?)"
    args = (program["id"], type, type, severity, severity)
    order = "CASE f.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,f.last_seen_scan DESC,f.id DESC"
    source = "FROM finding f LEFT JOIN asset a ON a.id=f.asset_id WHERE " + where
    with database.connect() as conn:
        response.headers["X-Total-Count"] = str(conn.execute("SELECT count(*) " + source, args).fetchone()[0])
        return [decoded(r) for r in conn.execute("SELECT f.*,a.host AS host " + source + " ORDER BY " + order + " LIMIT ? OFFSET ?", (*args, limit, offset))]


@router.get("/{slug}/summary")
def summary(slug: str, request: Request):
    """Everything the Program overview needs in one call (no list endpoints scraped by the UI)."""
    database = request.app.state.database
    program = program_row(database, slug)
    with database.connect() as conn:
        scan = conn.execute("SELECT * FROM scan_run WHERE program_id=? AND status IN ('done','done_partial') ORDER BY id DESC LIMIT 1", (program["id"],)).fetchone()
        latest = conn.execute("SELECT * FROM scan_run WHERE program_id=? AND status!='draft' ORDER BY id DESC LIMIT 1", (program["id"],)).fetchone()
        counts = {r[0]: r[1] for r in conn.execute("SELECT change,count(*) FROM diff_event WHERE program_id=? AND scan_run_id=? GROUP BY change", (program["id"], scan["id"] if scan else None))}
        severities = {r[0]: r[1] for r in conn.execute("SELECT severity,count(*) FROM finding WHERE program_id=? GROUP BY severity", (program["id"],))}
        top = [decoded(r) for r in conn.execute("SELECT * FROM asset WHERE program_id=? AND state='active' AND category!='cidr' ORDER BY rank_score DESC,host LIMIT 5", (program["id"],))]
        assets_total = conn.execute("SELECT count(*) FROM asset WHERE program_id=? AND state='active'", (program["id"],)).fetchone()[0]
        schedule = conn.execute("SELECT * FROM schedule WHERE program_id=?", (program["id"],)).fetchone()
        drafts = conn.execute("SELECT count(*) FROM scan_run WHERE program_id=? AND status='draft'", (program["id"],)).fetchone()[0]
    from backend.trust import scope_trust
    return {"slug": slug, "source": program["source"], "handle": program["handle"],
            "trust": scope_trust(program["source"], program["handle"], json.loads(program.get("policy_json") or "{}")),
            "default_profile_id": program.get("default_profile_id"),
            "target_path": str((request.app.state.settings.BBASM_TARGETS / slug).resolve()),
            **request.app.state.settings.hunt_target(slug),
            "latest_scan": decoded(latest) if latest else None,
            "last_completed_scan": decoded(scan) if scan else None,
            "changes": {k: counts.get(k, 0) for k in ("new", "changed", "gone")},
            "findings_by_severity": {k: severities.get(k, 0) for k in ("critical", "high", "medium", "low", "info")},
            "assets_active": assets_total, "top_surface": top, "draft_count": drafts,
            "schedule": dict(schedule) if schedule else None}


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


@router.post("/{slug}/rescan")
def rescan(slug: str, request: Request):
    """New draft from the program's stored scope (H1: re-fetched), so Review can adjust it again."""
    from backend.brief.generator import BriefGenerator
    from backend.models import ResolveRequest
    state = request.app.state
    program = program_row(state.database, slug)
    if program["source"] == "h1":
        body = ResolveRequest(input="h1:" + program["handle"])
    else:
        with state.database.connect() as conn:
            rules = [dict(r) for r in conn.execute("SELECT pattern,kind FROM scope_rule WHERE program_id=? ORDER BY id", (program["id"],))]
        body = ResolveRequest(input="raw", name=slug, scope=[r["pattern"] for r in rules if r["kind"] == "in"],
                              scope_out=[r["pattern"] for r in rules if r["kind"] == "out"])
    result = state.scope_resolver.resolve(body)
    BriefGenerator(state.settings, state.database).ensure_program(result.slug)
    return {"scan_id": result.scan_id, "slug": result.slug}


TAGS = ("api", "auth", "admin", "sensitive", "redirect-param", "id-param", "file-param", "upload", "js", "docs", "params", "static")


def _latest_completed(conn, program_id):
    row = conn.execute("SELECT id,stats_json FROM scan_run WHERE program_id=? AND status IN ('done','done_partial') ORDER BY id DESC LIMIT 1", (program_id,)).fetchone()
    return (row["id"], json.loads(row["stats_json"] or "{}")) if row else (None, {})


def _url_filter(program_id, scan, q, host, tag, verification, source, shape, min_score, include_static):
    clauses, args = ["u.program_id=?"], [program_id]
    if scan is not None:
        clauses.append("u.last_seen_scan=?")
        args.append(scan)
    if q:
        clauses.append("u.url LIKE ? ESCAPE '\\'")
        args.append("%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if host:
        clauses.append("a.host=?")
        args.append(host)
    if tag:
        clauses.append("u.tags_json LIKE ?")
        args.append('%"' + tag + '"%')
    elif not include_static:
        clauses.append("(u.tags_json IS NULL OR u.tags_json NOT LIKE '%\"static\"%')")
    for column, value in (("u.verification", verification), ("u.source", source), ("u.shape", shape)):
        if value:
            clauses.append(column + "=?")
            args.append(value)
    if min_score:
        clauses.append("COALESCE(u.score,0)>=?")
        args.append(min_score)
    return " AND ".join(clauses), args


@router.get("/{slug}/urls")
def urls(slug: str, request: Request, response: Response, q: str = Query("", max_length=500), host: str | None = Query(None, max_length=253),
         tag: str | None = Query(None, max_length=20), verification: Literal["historical", "observed", "live"] | None = None,
         source: str | None = Query(None, max_length=20), shape: str | None = Query(None, max_length=200),
         min_score: float = Query(0, ge=0, le=10), include_static: bool = False,
         scan: Literal["latest", "all"] = "latest",
         limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    """URLs that passed the scope gate, best first. Every row says how it was learned."""
    database = request.app.state.database
    program = program_row(database, slug)
    with database.connect() as conn:
        latest, _ = _latest_completed(conn, program["id"])
        where, args = _url_filter(program["id"], latest if scan == "latest" else None, q, host, tag, verification, source, shape, min_score, include_static)
        source_sql = "FROM url u LEFT JOIN asset a ON a.id=u.asset_id WHERE " + where
        response.headers["X-Total-Count"] = str(conn.execute("SELECT count(*) " + source_sql, args).fetchone()[0])
        rows = conn.execute("SELECT u.id,u.url,u.source,u.score,u.verification,u.shape,u.tags_json,u.first_seen_scan,u.last_seen_scan,a.host AS host " + source_sql
                            + " ORDER BY COALESCE(u.score,0) DESC,u.url LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
    return [{"id": r["id"], "url": r["url"], "host": r["host"], "source": r["source"], "score": r["score"] or 0,
             "verification": r["verification"] or "historical", "shape": r["shape"],
             "tags": json.loads(r["tags_json"] or "[]"), "first_seen_scan": r["first_seen_scan"],
             "is_new": r["first_seen_scan"] == latest} for r in rows]


@router.get("/{slug}/urls/summary")
def urls_summary(slug: str, request: Request, shapes: int = Query(25, ge=1, le=100)):
    """The funnel (what the tools produced -> what survived the scope gate) and the shape of the site."""
    database = request.app.state.database
    program = program_row(database, slug)
    with database.connect() as conn:
        latest, stats = _latest_completed(conn, program["id"])
        base = "program_id=? AND last_seen_scan=?"
        counts = {tag: conn.execute(f"SELECT count(*) FROM url WHERE {base} AND tags_json LIKE ?", (program["id"], latest, '%"' + tag + '"%')).fetchone()[0] for tag in TAGS}
        total = conn.execute(f"SELECT count(*) FROM url WHERE {base}", (program["id"], latest)).fetchone()[0]
        top_shapes = [{"shape": r["shape"], "count": r["n"], "max_score": r["top"], "example": r["example"]}
                      for r in conn.execute(f"SELECT shape,count(*) n,max(COALESCE(score,0)) top,min(url) example FROM url WHERE {base} AND (tags_json IS NULL OR tags_json NOT LIKE '%\"static\"%') GROUP BY shape ORDER BY top DESC,n DESC LIMIT ?", (program["id"], latest, shapes))]
        hosts = [{"host": r["host"], "count": r["n"]} for r in conn.execute(
            "SELECT a.host host,count(*) n FROM url u JOIN asset a ON a.id=u.asset_id WHERE u.program_id=? AND u.last_seen_scan=? GROUP BY a.host ORDER BY n DESC LIMIT 20",
            (program["id"], latest))]
    return {"scan_id": latest, "total": total, "funnel": stats.get("url_funnel"), "by_tag": counts, "top_shapes": top_shapes, "hosts": hosts}


@router.get("/{slug}/urls/export")
def urls_export(slug: str, request: Request, q: str = Query("", max_length=500), host: str | None = None, tag: str | None = Query(None, max_length=20),
                verification: Literal["historical", "observed", "live"] | None = None, shape: str | None = Query(None, max_length=200),
                min_score: float = Query(0, ge=0, le=10), include_static: bool = False, limit: int = Query(20000, ge=1, le=100000)):
    """Plain text, one URL per line — feed it to another tool or grep it."""
    database = request.app.state.database
    program = program_row(database, slug)
    with database.connect() as conn:
        latest, _ = _latest_completed(conn, program["id"])
        where, args = _url_filter(program["id"], latest, q, host, tag, verification, None, shape, min_score, include_static)
        rows = conn.execute("SELECT u.url FROM url u LEFT JOIN asset a ON a.id=u.asset_id WHERE " + where + " ORDER BY COALESCE(u.score,0) DESC,u.url LIMIT ?", (*args, limit)).fetchall()
    name = f"{slug}-urls" + (f"-{tag}" if tag else "") + ".txt"
    return PlainTextResponse("\n".join(r[0] for r in rows) + "\n", headers={"Content-Disposition": f'attachment; filename="{name}"'})
