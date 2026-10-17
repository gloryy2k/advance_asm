"""Portfolio, filtered surface/findings/diffs and monitoring control."""
import json
from typing import Literal

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

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


def _selected_completed_scan(conn, program_id: int, scan: str) -> int | None:
    """Resolve a result selector within this program; drafts and foreign scans are never historical results."""
    if scan == "all":
        return None
    if scan == "latest":
        row = conn.execute("SELECT id FROM scan_run WHERE program_id=? AND status IN ('done','done_partial') ORDER BY id DESC LIMIT 1", (program_id,)).fetchone()
    elif scan.isdigit() and int(scan) < 2**31:
        row = conn.execute("SELECT id FROM scan_run WHERE program_id=? AND id=? AND status IN ('done','done_partial')", (program_id, int(scan))).fetchone()
        if not row:
            raise ScopeError("Scan không tồn tại hoặc chưa hoàn tất trong program này", "invalid_scan")
    else:
        raise ScopeError("scan phải là latest, all hoặc số scan hoàn tất", "invalid_scan")
    return row[0] if row else None


@router.get("")
def portfolio(request: Request, include_drafts: bool = False, archived: Literal["exclude", "include", "only"] = "exclude"):
    database = request.app.state.database
    if not database.path.exists():
        return []
    result = []
    with database.connect() as conn:
        for program in conn.execute("SELECT * FROM program WHERE deleting_at IS NULL"):
            if (archived == "exclude" and program["archived_at"]) or (archived == "only" and not program["archived_at"]):
                continue
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


@router.get("/{slug}/scan-options")
def scan_options(slug: str, request: Request):
    """Small, complete selector list; detail only embeds the newest 100 full scan records."""
    database = request.app.state.database
    program = program_row(database, slug)
    with database.connect() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT id,depth,status,finished_at FROM scan_run WHERE program_id=? AND status IN ('done','done_partial') ORDER BY id DESC",
            (program["id"],),
        )]


@router.get("/{slug}/assets")
def assets(slug: str, request: Request, response: Response = None, state: Literal["active", "gone"] | None = None,
           min_rank: float = Query(0, ge=0, le=10), q: str = Query("", max_length=500),
           category: str | None = Query(None, max_length=20),
           limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
           scan: str = Query("all", max_length=12)):
    database = request.app.state.database
    program = program_row(database, slug)
    where = "program_id=? AND (? IS NULL OR state=?) AND COALESCE(rank_score,0)>=? AND host LIKE ? ESCAPE '\\' AND (? IS NULL OR category=?)"
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    args = (program["id"], state, state, min_rank, like, category, category)
    with database.connect() as conn:
        selected = _selected_completed_scan(conn, program["id"], scan)
        if scan == "latest" and selected is None:
            where += " AND 1=0"
        if selected is not None:
            # Asset status, tech and rank are mutable current fields. First/last seen only give an approximate
            # observation interval for an older scan, not a historical status snapshot.
            where += " AND first_seen_scan<=? AND last_seen_scan>=?" if scan != "latest" else " AND last_seen_scan=?"
            args += (selected, selected) if scan != "latest" else (selected,)
        if response is not None:
            response.headers["X-Total-Count"] = str(conn.execute("SELECT count(*) FROM asset WHERE " + where, args).fetchone()[0])
        return [decoded(r) for r in conn.execute("SELECT * FROM asset WHERE " + where + " ORDER BY rank_score DESC,host LIMIT ? OFFSET ?", (*args, limit, offset))]


@router.get("/{slug}/surface")
def surface(slug: str, request: Request, limit: int = Query(25, ge=1, le=1000), scan: str = Query("all", max_length=12)):
    return assets(slug, request, None, "active" if scan in ("all", "latest") else None, 0, "", None, limit, 0, scan)


def _resolve_scan_id(conn, program_id, scan):
    """A specific scan to read on-disk output for (ports/dirs live per scan folder, not a DB table). A draft never
    launched, so any file under its folder is a stale/orphaned leftover (V164_HOST_AUDIT.md), never this scan's own
    output — reject it the same way 'latest' already excludes everything before 'queued'."""
    if scan == "latest":
        row = conn.execute("SELECT id FROM scan_run WHERE program_id=? AND status IN ('done','done_partial') ORDER BY id DESC LIMIT 1", (program_id,)).fetchone()
        return row["id"] if row else None
    if scan.isdigit() and int(scan) < 2**31:
        row = conn.execute("SELECT id FROM scan_run WHERE program_id=? AND id=? AND status!='draft'", (program_id, int(scan))).fetchone()
        return row["id"] if row else None
    raise ScopeError("scan phải là latest hoặc số scan", "invalid_scan")


@router.get("/{slug}/ports")
def ports(slug: str, request: Request, scan: str = Query("latest", max_length=12)):
    """nmap results of one scan (BACKLOG mục 4: bảng "Cổng/Dịch vụ" riêng, không chỉ đọc lúc dựng Run). Luôn đọc
    lại từ đĩa — không có bảng DB cho dữ liệu này, cùng nguồn `backend.asm.results.summarize_ports` mà Run dùng."""
    from backend.asm import results as asm_results
    from backend.asm.phases import scan_root
    database, settings = request.app.state.database, request.app.state.settings
    program = program_row(database, slug)
    with database.connect() as conn:
        scan_id = _resolve_scan_id(conn, program["id"], scan)
    if scan_id is None:
        return {"found": False, "scan_id": None, "pairs": [], "hosts": 0, "unique_ports": 0, "complete": False,
                "files": [], "rows": [], "cdn": [], "cdn_hosts": [], "cdn_pairs": 0}
    return {**asm_results.summarize_ports(scan_root(settings, slug, scan_id)), "scan_id": scan_id}


@router.get("/{slug}/dirs")
def dirs(slug: str, request: Request, scan: str = Query("latest", max_length=12)):
    """ffuf results of one scan (BACKLOG mục 4: bảng "Đường dẫn dò được" riêng). Cùng nguồn
    `backend.asm.results.summarize_dirs` mà Run dùng; trang nhiễu (403 lặp…) đã bị loại ở đó."""
    from backend.asm import results as asm_results
    from backend.asm.phases import scan_root
    database, settings = request.app.state.database, request.app.state.settings
    program = program_row(database, slug)
    with database.connect() as conn:
        scan_id = _resolve_scan_id(conn, program["id"], scan)
    if scan_id is None:
        return {"found": False, "scan_id": None, "hosts": [], "total": 0, "noise": 0, "significant": 0, "blocked_only": []}
    return {**asm_results.summarize_dirs(scan_root(settings, slug, scan_id)), "scan_id": scan_id}


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
             limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
             scan: str = Query("all", max_length=12)):
    database = request.app.state.database
    program = program_row(database, slug)
    where = "f.program_id=? AND (? IS NULL OR f.type=?) AND (? IS NULL OR f.severity=?)"
    args = (program["id"], type, type, severity, severity)
    order = "CASE f.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,f.last_seen_scan DESC,f.id DESC"
    with database.connect() as conn:
        selected = _selected_completed_scan(conn, program["id"], scan)
        if scan == "latest" and selected is None:
            where += " AND 1=0"
        if selected is not None:
            where += " AND f.first_seen_scan<=? AND f.last_seen_scan>=?" if scan != "latest" else " AND f.last_seen_scan=?"
            args += (selected, selected) if scan != "latest" else (selected,)
        source = "FROM finding f LEFT JOIN asset a ON a.id=f.asset_id WHERE " + where
        response.headers["X-Total-Count"] = str(conn.execute("SELECT count(*) " + source, args).fetchone()[0])
        return [decoded(r) for r in conn.execute("SELECT f.*,a.host AS host " + source + " ORDER BY " + order + " LIMIT ? OFFSET ?", (*args, limit, offset))]


def _schedule_view(row):
    """The schedule as the page shows it: what will actually run, so enabling it is never a blind click. Header *names* only."""
    if not row:
        return None
    view = dict(row)
    try:
        config = ScanConfig.model_validate_json(view.pop("config_json") or "{}")
    except ValueError:
        return view
    view["config"] = {"depth": config.depth, "threads": config.threads, "rate_limit": config.rate_limit,
                      "request_header_names": [h.split(":", 1)[0].strip() for h in config.request_headers],
                      "skipped_headers": config.skipped_headers}
    return view


TREND_SCANS = 30
SEVERITIES = ("critical", "high", "medium", "low", "info")


@router.get("/{slug}/charts")
def charts(slug: str, request: Request):
    """Numbers behind the Overview charts: the trend across completed scans and what the current inventory looks like.
    Every series is also shown as text/table by the page, so none of it relies on colour alone."""
    from collections import Counter
    database = request.app.state.database
    program = program_row(database, slug)
    pid = program["id"]
    with database.connect() as conn:
        scans = [dict(r) for r in conn.execute(
            "SELECT id,depth,status,finished_at,stats_json FROM scan_run WHERE program_id=? AND status IN ('done','done_partial') ORDER BY id DESC LIMIT ?",
            (pid, TREND_SCANS))][::-1]
        changes = {}
        if scans:
            marks = ",".join("?" * len(scans))
            for scan_id, change, n in conn.execute(
                    f"SELECT scan_run_id,change,count(*) FROM diff_event WHERE program_id=? AND scan_run_id IN ({marks}) GROUP BY scan_run_id,change",
                    (pid, *[s["id"] for s in scans])):
                changes.setdefault(scan_id, {})[change] = n
        assets = conn.execute("SELECT id,host,status_code,tech_json FROM asset WHERE program_id=? AND state='active'", (pid,)).fetchall()
        by_asset = {r["id"]: r["host"] for r in assets}
        url_rows = conn.execute("SELECT asset_id,count(*),max(COALESCE(score,0)) FROM url WHERE program_id=? AND asset_id IS NOT NULL GROUP BY asset_id", (pid,)).fetchall()
        finding_rows = conn.execute("SELECT asset_id,severity,count(*) FROM finding WHERE program_id=? GROUP BY asset_id,severity", (pid,)).fetchall()
    trend = []
    for scan in scans:
        stats = json.loads(scan.pop("stats_json") or "{}")
        diff = changes.get(scan["id"], {})
        trend.append({**scan, "hosts": stats.get("subs"), "live": stats.get("live"), "urls": stats.get("urls"), "findings": stats.get("findings"),
                      "new": diff.get("new", 0), "changed": diff.get("changed", 0), "gone": diff.get("gone", 0)})
    classes = Counter()
    codes = Counter()
    tech = Counter()
    for asset in assets:
        code = asset["status_code"]
        classes[f"{code // 100}xx" if code else "none"] += 1
        if code:
            codes[code] += 1
        try:
            tech.update(set(json.loads(asset["tech_json"] or "[]")))
        except ValueError:
            pass
    hosts = sorted(((by_asset[a], n, score) for a, n, score in url_rows if a in by_asset), key=lambda r: (-r[1], r[0]))[:10]
    per_host = {}
    for asset_id, severity, n in finding_rows:
        host = by_asset.get(asset_id, "(không gắn host)")
        per_host.setdefault(host, Counter())[severity or "info"] += n
    matrix_hosts = sorted(per_host.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))[:8]
    return {
        "trend": trend, "truncated": len(trend) == TREND_SCANS,
        "status": {"classes": dict(classes), "codes": [{"code": c, "count": n} for c, n in codes.most_common(8)], "total": len(assets)},
        "tech": [{"name": name, "count": n} for name, n in sorted(tech.items(), key=lambda kv: (-kv[1], kv[0]))[:10]],
        "hosts_by_urls": [{"host": h, "urls": n, "top_score": round(score, 1)} for h, n, score in hosts],
        "severity_matrix": {"severities": list(SEVERITIES), "hosts": [{"host": h, **{s: c.get(s, 0) for s in SEVERITIES}} for h, c in matrix_hosts]},
    }


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
        assets_live = conn.execute("SELECT count(*) FROM asset WHERE program_id=? AND state='active' AND status_code IS NOT NULL", (program["id"],)).fetchone()[0]
        assets_gone = conn.execute("SELECT count(*) FROM asset WHERE program_id=? AND state='gone'", (program["id"],)).fetchone()[0]
        schedule = conn.execute("SELECT * FROM schedule WHERE program_id=?", (program["id"],)).fetchone()
        drafts = conn.execute("SELECT count(*) FROM scan_run WHERE program_id=? AND status='draft'", (program["id"],)).fetchone()[0]
    from backend.trust import required_headers, scope_trust
    notes = (json.loads(scan["stats_json"] or "{}").get("repairs") or []) if scan else []
    return {"slug": slug, "source": program["source"], "handle": program["handle"], "archived_at": program.get("archived_at"),
            "data_notes": notes,
            "trust": scope_trust(program["source"], program["handle"], json.loads(program.get("policy_json") or "{}")),
            "default_profile_id": program.get("default_profile_id"),
            "request_headers": json.loads(program.get("request_headers_json") or "[]"),
            "request_header_hints": required_headers(json.loads(program.get("policy_json") or "{}")),
            "target_path": str((request.app.state.settings.BBASM_TARGETS / slug).resolve()),
            **request.app.state.settings.hunt_target(slug),
            "latest_scan": decoded(latest) if latest else None,
            "last_completed_scan": decoded(scan) if scan else None,
            "changes": {k: counts.get(k, 0) for k in ("new", "changed", "gone")},
            "findings_by_severity": {k: severities.get(k, 0) for k in ("critical", "high", "medium", "low", "info")},
            "assets_active": assets_total, "top_surface": top, "draft_count": drafts,
            "schedule": _schedule_view(schedule), "assets_live": assets_live, "assets_gone": assets_gone}


class ScheduleRequest(BaseModel):
    interval: Literal["6h", "daily", "weekly"]
    depth: Literal["passive", "light", "strong"]
    enabled: bool = True
    config: ScanConfig | None = None
    # Policy headers the user read about and knowingly does not send, and the consent to scan automatically.
    skipped_headers: list[str] = Field(default_factory=list, max_length=5)
    automation_ack: bool = False


class RequestHeaders(BaseModel):
    headers: list[str] = Field(default_factory=list, max_length=5)


@router.put("/{slug}/request-headers")
def set_request_headers(slug: str, body: RequestHeaders, request: Request):
    """Default headers for every request to this program's targets (e.g. the one its policy requires)."""
    from backend.models import validate_header
    database = request.app.state.database
    from backend.lifecycle import require_active
    require_active(program_row(database, slug))
    try:
        headers = [validate_header(item) for item in body.headers]
    except ValueError as exc:
        raise ScopeError(str(exc), "invalid_header") from None
    with database.connect() as conn, conn:
        conn.execute("UPDATE program SET request_headers_json=? WHERE slug=?", (json.dumps(headers) if headers else None, slug))
    return {"slug": slug, "request_headers": headers}


@router.post("/{slug}/schedule")
async def schedule(slug: str, body: ScheduleRequest, request: Request):
    state = request.app.state
    program = program_row(state.database, slug)
    with state.database.connect() as conn:
        entries = [classify(r["pattern"], r["kind"], r["asset_type"]) for r in conn.execute("SELECT * FROM scope_rule WHERE program_id=?", (program["id"],))]
    policy = json.loads(program.get("policy_json") or "{}")
    from backend.api.scans import require_ack, require_gate, require_headers
    from backend.jobs.scope_resolver import program_config
    from backend.trust import launch_gate, required_headers
    with state.database.connect() as conn:
        entries = [classify(r["pattern"], r["kind"], r["asset_type"]) for r in conn.execute("SELECT * FROM scope_rule WHERE program_id=?", (program["id"],))]
        config = body.config or program_config(state.settings, conn, program, entries, body.depth)
    if body.skipped_headers and not body.config:
        config = ScanConfig.model_validate({**config.model_dump(), "skipped_headers": body.skipped_headers})
    if config.depth != body.depth:
        raise ScopeError("depth must match config.depth")
    if not body.enabled:
        # Switching monitoring off keeps the stored configuration; it needs neither consent nor a header.
        with state.database.connect() as conn:
            row = conn.execute("SELECT interval,config_json FROM schedule WHERE program_id=?", (program["id"],)).fetchone()
        if row:
            return state.scheduler.configure(program["id"], row["interval"], ScanConfig.model_validate_json(row["config_json"]), False)
    else:
        from backend.lifecycle import require_active
        require_active(program)
        require_ack(config.depth, body.automation_ack)
        require_gate(config.depth, launch_gate(program["source"], policy))
        require_headers(config, required_headers(policy))
        from backend.api.scans import require_apex, require_ffuf
        require_ffuf(config)
        require_apex(config)
    saved = state.scheduler.configure(program["id"], body.interval, config, body.enabled)
    if body.enabled and config.depth != "passive":
        from backend.scope_gate import audit
        sent = [h.split(":", 1)[0].strip() for h in config.request_headers]
        audit(state.settings.BBASM_TARGETS / slug / "audit.jsonl", slug, "ack", "automation_ack_by_user", schedule=body.interval,
              depth=config.depth, headers_sent=sent, headers_skipped=config.skipped_headers)
    return saved


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


def _url_scope(scan, latest):
    """Which scans a URL list speaks for. 'latest': URLs the newest completed scan saw. 'all': everything on record
    (history across scans). A number N: URLs recorded by scan N or earlier -- the store keeps first/last seen, not a
    per-scan membership, so this is 'known as of scan N', never 'exactly what scan N found'."""
    if scan == "all":
        return None
    if scan == "latest":
        return ("u.last_seen_scan=?", latest)
    if scan.isdigit() and int(scan) < 2**31:
        return ("u.first_seen_scan<=?", int(scan))
    raise ScopeError("scan phải là latest, all hoặc số scan", "invalid_scan")


def _url_filter(program_id, scope, q, host, tag, verification, source, shape, min_score, include_static):
    clauses, args = ["u.program_id=?"], [program_id]
    if scope is not None:
        clauses.append(scope[0])
        args.append(scope[1])
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
         scan: str = Query("latest", max_length=12),
         limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    """URLs that passed the scope gate, best first. Every row says how it was learned."""
    database = request.app.state.database
    program = program_row(database, slug)
    with database.connect() as conn:
        latest, _ = _latest_completed(conn, program["id"])
        where, args = _url_filter(program["id"], _url_scope(scan, latest), q, host, tag, verification, source, shape, min_score, include_static)
        source_sql = "FROM url u LEFT JOIN asset a ON a.id=u.asset_id WHERE " + where
        response.headers["X-Total-Count"] = str(conn.execute("SELECT count(*) " + source_sql, args).fetchone()[0])
        rows = conn.execute("SELECT u.id,u.url,u.source,u.score,u.verification,u.shape,u.tags_json,u.first_seen_scan,u.last_seen_scan,a.host AS host " + source_sql
                            + " ORDER BY COALESCE(u.score,0) DESC,u.url LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
    return [{"id": r["id"], "url": r["url"], "host": r["host"], "source": r["source"], "score": r["score"] or 0,
             "verification": r["verification"] or "historical", "shape": r["shape"],
             "tags": json.loads(r["tags_json"] or "[]"), "first_seen_scan": r["first_seen_scan"], "last_seen_scan": r["last_seen_scan"],
             "is_new": r["first_seen_scan"] == latest} for r in rows]


@router.get("/{slug}/urls/summary")
def urls_summary(slug: str, request: Request, shapes: int = Query(25, ge=1, le=100), scan: str = Query("latest", max_length=12)):
    """The funnel (what the tools produced -> what survived the scope gate) and the shape of the site."""
    database = request.app.state.database
    program = program_row(database, slug)
    with database.connect() as conn:
        latest, stats = _latest_completed(conn, program["id"])
        scope = _url_scope(scan, latest)
        base = "program_id=?" + (" AND " + scope[0].replace("u.", "") if scope else "")
        base_args = (program["id"], *([scope[1]] if scope else []))
        counts = {tag: conn.execute(f"SELECT count(*) FROM url WHERE {base} AND tags_json LIKE ?", (*base_args, '%"' + tag + '"%')).fetchone()[0] for tag in TAGS}
        total = conn.execute(f"SELECT count(*) FROM url WHERE {base}", base_args).fetchone()[0]
        history_total = conn.execute("SELECT count(*) FROM url WHERE program_id=?", (program["id"],)).fetchone()[0]
        latest_row = conn.execute("SELECT id,depth,status,finished_at FROM scan_run WHERE id=?", (latest,)).fetchone() if latest else None
        top_shapes = [{"shape": r["shape"], "count": r["n"], "max_score": r["top"], "example": r["example"]}
                      for r in conn.execute(f"SELECT shape,count(*) n,max(COALESCE(score,0)) top,min(url) example FROM url WHERE {base} AND (tags_json IS NULL OR tags_json NOT LIKE '%\"static\"%') GROUP BY shape ORDER BY top DESC,n DESC LIMIT ?", (*base_args, shapes))]
        hosts = [{"host": r["host"], "count": r["n"]} for r in conn.execute(
            "SELECT a.host host,count(*) n FROM url u JOIN asset a ON a.id=u.asset_id WHERE " + base.replace("program_id", "u.program_id").replace("last_seen_scan", "u.last_seen_scan").replace("first_seen_scan", "u.first_seen_scan")
            + " GROUP BY a.host ORDER BY n DESC LIMIT 20", base_args)]
    return {"scan_id": latest, "scope": scan, "latest": dict(latest_row) if latest_row else None, "history_total": history_total, "total": total, "funnel": stats.get("url_funnel") if scan == "latest" else None, "by_tag": counts, "top_shapes": top_shapes, "hosts": hosts}


def _like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/{slug}/urls/tree")
def urls_tree(slug: str, request: Request, host: str | None = Query(None, max_length=260), prefix: str = Query("", max_length=1000),
              q: str = Query("", max_length=500), tag: str | None = Query(None, max_length=20),
              verification: Literal["historical", "observed", "live"] | None = None, min_score: float = Query(0, ge=0, le=10),
              include_static: bool = True, scan: str = Query("latest", max_length=12),
              sort: Literal["az", "score", "count"] = "az", folders_first: bool = False,
              depth: int = Query(1, ge=1, le=12), limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0)):
    """One level of the sitemap: the hosts (no `host`), or the folders/files under `host`+`prefix`. Same filters and scan
    scope as /urls. `depth` > 1 returns nested levels (capped), used by "expand to level N" and by search."""
    from backend.sitemap import MAX_NODES, MAX_ROWS, Budget, build_level, parse_rows
    database = request.app.state.database
    program = program_row(database, slug)
    with database.connect() as conn:
        latest, _ = _latest_completed(conn, program["id"])
        where, args = _url_filter(program["id"], _url_scope(scan, latest), q, None, tag, verification, None, None, min_score, include_static)
        if host:
            clean = host.lower()
            where += " AND (u.url LIKE ? ESCAPE '\\' OR u.url LIKE ? ESCAPE '\\')"
            args += [f"%://{_like(clean)}/%", f"%://{_like(clean)}"]
        rows = conn.execute("SELECT u.url,u.source,u.score,u.verification,u.tags_json,u.first_seen_scan,u.last_seen_scan FROM url u WHERE " + where
                            + " LIMIT ?", (*args, MAX_ROWS + 1)).fetchall()
    truncated_rows = len(rows) > MAX_ROWS
    parsed = parse_rows(rows[:MAX_ROWS])
    segments = [part for part in prefix.split("/") if part]
    budget = Budget(MAX_NODES)
    nodes, total = build_level(parsed, host.lower() if host else None, segments if host else [], depth=depth, sort=sort,
                               folders_first=folders_first, limit=limit, offset=offset, latest=latest, budget=budget)
    return {"scan": scan, "scan_id": latest, "host": host, "prefix": "/" + "/".join(segments) if segments else "/",
            "nodes": nodes, "total": total, "matched": len(parsed), "truncated": truncated_rows or budget.truncated}


@router.get("/{slug}/urls/export")
def urls_export(slug: str, request: Request, q: str = Query("", max_length=500), host: str | None = None, tag: str | None = Query(None, max_length=20),
                verification: Literal["historical", "observed", "live"] | None = None, shape: str | None = Query(None, max_length=200),
                min_score: float = Query(0, ge=0, le=10), include_static: bool = False, limit: int = Query(20000, ge=1, le=100000),
                scan: str = Query("latest", max_length=12)):
    """Plain text, one URL per line — feed it to another tool or grep it."""
    database = request.app.state.database
    program = program_row(database, slug)
    with database.connect() as conn:
        latest, _ = _latest_completed(conn, program["id"])
        where, args = _url_filter(program["id"], _url_scope(scan, latest), q, host, tag, verification, None, shape, min_score, include_static)
        rows = conn.execute("SELECT u.url FROM url u LEFT JOIN asset a ON a.id=u.asset_id WHERE " + where + " ORDER BY COALESCE(u.score,0) DESC,u.url LIMIT ?", (*args, limit)).fetchall()
    name = f"{slug}-urls" + ("" if scan == "latest" else f"-{scan}") + (f"-{tag}" if tag else "") + ".txt"
    return PlainTextResponse("\n".join(r[0] for r in rows) + "\n", headers={"Content-Disposition": f'attachment; filename="{name}"'})


class ConfirmDelete(BaseModel):
    confirm_slug: str = Field(max_length=200)


@router.post("/{slug}/archive")
def archive_program(slug: str, request: Request):
    """Hide the program from the portfolio and pause its schedule. History, Diff, findings and files stay."""
    from backend import lifecycle
    state = request.app.state
    program_row(state.database, slug)
    return lifecycle.archive(state.database, state.scheduler, state.settings, slug)


@router.post("/{slug}/restore")
def restore_program(slug: str, request: Request):
    from backend import lifecycle
    state = request.app.state
    program_row(state.database, slug)
    return lifecycle.restore(state.database, state.settings, slug)


@router.get("/{slug}/delete-preview")
def delete_preview(slug: str, request: Request):
    """What a permanent delete would remove, for the confirmation screen. Deletes nothing."""
    from backend import lifecycle
    state = request.app.state
    program_row(state.database, slug)
    return lifecycle.preview(state.database, state.settings, slug)


@router.delete("/{slug}")
def delete_program(slug: str, body: ConfirmDelete, request: Request):
    """Permanent delete of an ARCHIVED program: database rows, files under targets/<slug>, logs. Needs the program's name typed."""
    from backend import lifecycle
    state = request.app.state
    program_row(state.database, slug)
    return lifecycle.delete(state.database, state.scheduler, state.runner, state.settings, slug, body.confirm_slug)
