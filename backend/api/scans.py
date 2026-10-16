"""P2 scan control endpoints; portfolio/query endpoints follow in P5."""

import asyncio

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse

from backend.models import LaunchRequest, ScanConfig
from backend.models import ResolveRequest
from backend.jobs.scope_resolver import default_config
from pydantic import BaseModel, Field
from typing import Literal
from backend.jobs.scope_resolver import ScopeError

router = APIRouter()


def require_gate(depth: str, gate: dict):
    """Light/Strong need enough verified scope + policy data; the Review page shows why, the API enforces it."""
    if depth != "passive" and depth not in gate.get("allowed_depths", []):
        raise ScopeError("Chưa đủ dữ liệu scope/policy để chạy " + depth + ": " + " ".join(gate.get("reasons", [])), "scope_incomplete")


def require_headers(config, hints):
    """Policy names a header (e.g. X-HackerOne-Research) that the config neither sends nor was told to skip: Light/Strong
    stop here. The confirmation is per header name (skipped_headers), so a header the policy adds later is not covered by
    an old answer. The value itself is never invented."""
    if config.depth == "passive" or config.skip_required_headers:
        return
    covered = {h.split(":", 1)[0].strip().lower() for h in config.request_headers} | {n.lower() for n in config.skipped_headers}
    missing = [name for name in hints or [] if name.lower() not in covered]
    if missing:
        raise ScopeError("Policy yêu cầu header " + ", ".join(missing) + " nhưng scan chưa cấu hình. Điền giá trị ở bước Review, "
                         "hoặc xác nhận đã đọc policy và bỏ qua (skipped_headers).", "header_required")


def require_ffuf(config):
    """Strong's directory brute-force (ffuf) needs the user's explicit word that the policy allows it, or must be switched off."""
    if config.depth == "strong" and not config.skip_ffuf and not config.ffuf_confirmed:
        raise ScopeError("Strong sẽ dò thư mục bằng ffuf (đoán đường dẫn). Xác nhận policy cho phép, hoặc tắt bước dò thư mục.",
                         "ffuf_confirm_required")


def require_apex(config):
    """Adding the apex of a wildcard widens the scope the program published: only with the user's explicit confirmation."""
    if config.include_apex and not config.apex_confirmed:
        raise ScopeError("Bạn chọn thêm domain gốc (" + ", ".join(config.include_apex) + ") vào scope. Xác nhận bạn đã đối chiếu policy chính thức cho phép, "
                         "hoặc bỏ lựa chọn này.", "apex_confirm_required")


class AutoScanRequest(BaseModel):
    input: str
    scope: list[str] = []
    depth: Literal["passive", "light", "strong"]
    config: ScanConfig | None = None
    automation_ack: bool = False


def require_ack(depth: str, acked: bool):
    """Anything above passive touches the target. The UI asks; the API enforces, so a direct client cannot skip it."""
    if depth != "passive" and not acked:
        raise ScopeError("Scan chủ động (light/strong) cần xác nhận chương trình cho phép công cụ tự động (automation_ack=true).",
                         "ack_required")


@router.post("/api/scans")
async def auto_scan(body: AutoScanRequest, request: Request):
    state = request.app.state
    if body.config and body.depth != body.config.depth:
        raise ScopeError("depth must match config.depth")
    require_ack(body.depth, body.automation_ack)
    await asyncio.to_thread(state.database.migrate)
    result = await asyncio.to_thread(state.scope_resolver.resolve, ResolveRequest(input=body.input, scope=body.scope))
    from backend.brief.generator import BriefGenerator
    BriefGenerator(state.settings, state.database).ensure_program(result.slug)
    config = body.config or default_config(state.settings.model_copy(update={"BBASM_DEFAULT_DEPTH": body.depth}),
        [entry for group in result.assets_by_category.values() for entry in group])
    try:
        review = await asyncio.to_thread(state.runner.review, result.scan_id)
        require_gate(config.depth, review["launch_gate"])
        require_headers(config, review["request_header_hints"])
        require_ffuf(config)
        require_apex(config)
    except ScopeError:
        await asyncio.to_thread(state.runner.delete_draft, result.scan_id)  # do not leave a draft nobody asked to keep
        raise
    await state.runner.submit(result.scan_id, config, ack=body.automation_ack)
    return {"scan_id": result.scan_id, "slug": result.slug, "status": "queued"}


@router.get("/api/scans/{scan_id}")
async def status(scan_id: int, request: Request):
    return await asyncio.to_thread(request.app.state.runner.status, scan_id)


@router.get("/api/scans/{scan_id}/config", response_model=ScanConfig)
async def get_config(scan_id: int, request: Request):
    return await asyncio.to_thread(request.app.state.runner.config, scan_id)


@router.put("/api/scans/{scan_id}/config", response_model=ScanConfig)
async def put_config(scan_id: int, config: ScanConfig, request: Request):
    return await asyncio.to_thread(request.app.state.runner.config, scan_id, config)


@router.get("/api/meta/phases")
async def phase_catalog():
    """Names and one-line explanations of every step — the Help page and Run page read the same list."""
    from backend.asm.phases import PHASES
    return [{k: p[k] for k in ("key", "title", "what", "touches", "tools", "count_label", "view")} | {"files": p["files"]} for p in PHASES]


@router.post("/api/meta/plan")
async def plan_preview(config: ScanConfig, request: Request):
    from backend.asm.phases import plan_for
    state = request.app.state
    return {"phases": plan_for(config, state.settings, state.runner.orchestrator.missing_tools())}


@router.post("/api/scans/{scan_id}/coverage")
async def scan_coverage(scan_id: int, config: ScanConfig, request: Request):
    """What this configuration will do with each asset of the scope, and the apex-domain question for each wildcard. Nothing runs."""
    from backend.coverage import coverage_summary, scope_coverage
    from backend.jobs.runner import JobRunner
    from backend.scope_selection import apex_candidates, effective_gate
    state = request.app.state
    review = await asyncio.to_thread(state.runner.review, scan_id)
    entries = review["scope"]
    rows = scope_coverage(entries, config)

    def build():
        import json
        with state.database.connect() as conn:
            scan = conn.execute("SELECT program_id FROM scan_run WHERE id=?", (scan_id,)).fetchone()
            latest = conn.execute("SELECT stats_json FROM scan_run WHERE program_id=? AND status IN ('done','done_partial') ORDER BY id DESC LIMIT 1", (scan["program_id"],)).fetchone()
        dropped = {h["host"]: h["count"] for h in (json.loads(latest[0] or "{}").get("url_funnel") or {}).get("out_of_scope_hosts", [])} if latest else {}
        explicit = {e["pattern"].lower() for e in entries if e["kind"] == "in" and e["category"] != "wildcard"}
        probe = config.model_copy(update={"include_apex": [], "apex_confirmed": False})
        apex = []
        for domain, wildcard in apex_candidates(entries).items():
            with_apex = effective_gate(entries, probe.model_copy(update={"include_apex": [domain], "apex_confirmed": True}),
                                       state.settings.BBASM_DATA / "coverage-probe.jsonl", state.settings)
            if domain in explicit or any(urlish.split("://")[-1].split("/")[0] == domain for urlish in explicit):
                status = "in_scope_explicit"
            elif not with_apex.in_scope(domain):
                status = "blocked_by_out"
            elif domain in config.include_apex and config.apex_confirmed:
                status = "added_by_you"
            else:
                status = "not_in_scope"
            apex.append({"apex": domain, "wildcard": wildcard, "status": status, "dropped_urls": dropped.get(domain, 0),
                         "selected": domain in config.include_apex, "confirmed": config.apex_confirmed})
        return apex
    apex = await asyncio.to_thread(build)
    gate = effective_gate(entries, config, state.settings.BBASM_DATA / "coverage-probe.jsonl", state.settings)
    hosts = gate.path_rule_hosts()
    # How an OUT rule about a PATH is held, tool by tool (the tools take hosts, not paths).
    enforcement = [
        {"tool": "Scope gate (mọi lệnh)", "how": "Chặn URL khớp đường dẫn OUT trước khi nhập kết quả; không có URL OUT nào được lưu.", "stops_request": False},
        {"tool": "gau / Wayback / crt.sh", "how": "Chỉ đọc nguồn công khai, không gửi request tới target; URL OUT bị lọc khỏi kết quả.", "stops_request": True},
        {"tool": "httpx (probe)", "how": "Chỉ hỏi gốc của host; host có OUT theo đường dẫn chỉ được probe, không được quét sâu (trừ khi bạn cho phép).", "stops_request": True},
        {"tool": "katana / nuclei / ffuf / nmap", "how": "KHÔNG thi hành được loại trừ theo đường dẫn: các host này bị khóa ở mức probe. Nếu bạn bật “cho phép công cụ chủ động”, request có thể tới đường dẫn OUT.", "stops_request": not config.allow_active_on_path_rules},
    ] if hosts else []
    shares = [{"key": key, "until": share, "seconds": int(config.scan_timeout * share)} for key, share in JobRunner.STAGES["active"]]
    return {"assets": rows, "summary": coverage_summary(rows), "apex": apex, "stage_shares": shares,
            "path_rules": {"hosts": hosts, "enforcement": enforcement, "active_allowed": config.allow_active_on_path_rules}}


_REPORT_CACHE: dict = {}
_REPORT_LOCKS: dict = {}


@router.get("/api/scans/{scan_id}/phases")
async def scan_phases(scan_id: int, request: Request):
    """Per-step report. Building it walks the scan's output directory; on a slow disk (Docker bind mounts) the Run page
    polling it every few seconds used to pile up requests and starve everything else. One build at a time per scan, and a
    slow result is reused for a short while (a fast one is never cached, so tests and quick disks always see fresh data)."""
    import time
    from backend.asm.phases import build_report
    state = request.app.state
    hit = _REPORT_CACHE.get(scan_id)
    if hit and time.monotonic() < hit[0]:
        return hit[1]
    async with _REPORT_LOCKS.setdefault(scan_id, asyncio.Lock()):
        hit = _REPORT_CACHE.get(scan_id)
        if hit and time.monotonic() < hit[0]:
            return hit[1]
        started = time.monotonic()
        report = await asyncio.to_thread(build_report, state.settings, state.database, scan_id, state.runner.orchestrator.missing_tools())
        took = time.monotonic() - started
        if report is None:
            raise ScopeError("Scan not found", "scan_not_found")
        if took > 0.5:
            _REPORT_CACHE[scan_id] = (time.monotonic() + min(10.0, 3 * took), report)
        return report


@router.get("/api/scans/{scan_id}/artifact")
async def scan_artifact(scan_id: int, request: Request, path: str = Query(..., max_length=300),
                        offset: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=1000),
                        q: str = Query("", max_length=200), reveal: bool = False):
    from backend.asm.phases import read_artifact
    state = request.app.state
    page = await asyncio.to_thread(read_artifact, state.settings, state.database, scan_id, path, offset=offset, limit=limit, query=q, reveal=reveal)
    if page is None:
        raise ScopeError("Không đọc được file này (không tồn tại hoặc ngoài thư mục scan).", "artifact_unavailable")
    return page


@router.get("/api/scans/{scan_id}/artifact/download")
async def scan_artifact_download(scan_id: int, request: Request, path: str = Query(..., max_length=300), reveal: bool = False):
    from backend.asm.phases import read_artifact, redacted_lines, scan_root
    state = request.app.state
    ok = await asyncio.to_thread(read_artifact, state.settings, state.database, scan_id, path, limit=1)
    if ok is None:
        raise ScopeError("Không đọc được file này (không tồn tại hoặc ngoài thư mục scan).", "artifact_unavailable")
    slug = (await asyncio.to_thread(state.runner.review, scan_id))["slug"]
    target = scan_root(state.settings, slug, scan_id) / path
    if reveal:
        return FileResponse(target, filename=f"scan{scan_id}-{ok['name']}", media_type="text/plain")
    # The default download hides credentials, same as the viewer; raw needs reveal=true.
    return StreamingResponse(redacted_lines(target, ok["name"]), media_type="text/plain",
                             headers={"Content-Disposition": f'attachment; filename="scan{scan_id}-{ok["name"]}"'})



class DeleteDrafts(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


@router.post("/api/drafts/delete")
async def delete_drafts(body: DeleteDrafts, request: Request):
    """Delete the chosen drafts. Each is re-checked inside the transaction (it may have been launched since the list was
    shown); anything that is no longer a draft is skipped and reported, never deleted."""
    return await asyncio.to_thread(request.app.state.runner.delete_drafts, body.ids)


@router.get("/api/drafts")
async def drafts(request: Request):
    return await asyncio.to_thread(request.app.state.runner.drafts)


@router.delete("/api/scans/{scan_id}")
async def delete_draft(scan_id: int, request: Request):
    await asyncio.to_thread(request.app.state.runner.delete_draft, scan_id)
    return {"deleted": scan_id}


@router.post("/api/scans/{scan_id}/launch")
async def launch(scan_id: int, body: LaunchRequest, request: Request):
    runner = request.app.state.runner
    config = body.config or await asyncio.to_thread(runner.config, scan_id)
    depth = config.depth
    require_ack(depth, body.automation_ack)
    review = await asyncio.to_thread(runner.review, scan_id)
    require_gate(depth, review["launch_gate"])
    require_headers(config, review["request_header_hints"])
    require_ffuf(config)
    require_apex(config)
    await runner.submit(scan_id, body.config, ack=body.automation_ack)
    return {"scan_id": scan_id, "status": "queued"}


@router.get("/api/scans/{scan_id}/review")
async def review(scan_id: int, request: Request):
    """Everything the Review/Run pages need in one call: scope, policy, warnings, target path."""
    return await asyncio.to_thread(request.app.state.runner.review, scan_id)


@router.post("/api/scans/{scan_id}/cancel")
async def cancel(scan_id: int, request: Request):
    await request.app.state.runner.cancel(scan_id)
    return await asyncio.to_thread(request.app.state.runner.status, scan_id)


@router.websocket("/ws/scan/{scan_id}")
async def scan_logs(scan_id: int, websocket: WebSocket, after: int = 0):
    runner = websocket.app.state.runner
    try:
        await asyncio.to_thread(runner.status, scan_id)
    except ScopeError:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        async for event in runner.logs.stream(scan_id, after=max(0, after)):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    await websocket.close()
