"""P2 scan control endpoints; portfolio/query endpoints follow in P5."""

import asyncio

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from backend.models import LaunchRequest, ScanConfig
from backend.models import ResolveRequest
from backend.jobs.scope_resolver import default_config
from pydantic import BaseModel
from typing import Literal
from backend.jobs.scope_resolver import ScopeError

router = APIRouter()


class AutoScanRequest(BaseModel):
    input: str
    scope: list[str] = []
    depth: Literal["passive", "light", "strong"]
    config: ScanConfig | None = None


@router.post("/api/scans")
async def auto_scan(body: AutoScanRequest, request: Request):
    state = request.app.state
    if body.config and body.depth != body.config.depth:
        raise ScopeError("depth must match config.depth")
    await asyncio.to_thread(state.database.migrate)
    result = await asyncio.to_thread(state.scope_resolver.resolve, ResolveRequest(input=body.input, scope=body.scope))
    from backend.brief.generator import BriefGenerator
    BriefGenerator(state.settings, state.database).ensure_program(result.slug)
    config = body.config or default_config(state.settings.model_copy(update={"BBASM_DEFAULT_DEPTH": body.depth}),
        [entry for group in result.assets_by_category.values() for entry in group])
    await state.runner.submit(result.scan_id, config)
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


@router.get("/api/scans/{scan_id}/phases")
async def scan_phases(scan_id: int, request: Request):
    from backend.asm.phases import build_report
    state = request.app.state
    report = await asyncio.to_thread(build_report, state.settings, state.database, scan_id, state.runner.orchestrator.missing_tools())
    if report is None:
        raise ScopeError("Scan not found", "scan_not_found")
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
async def scan_artifact_download(scan_id: int, request: Request, path: str = Query(..., max_length=300)):
    from backend.asm.phases import read_artifact, scan_root
    state = request.app.state
    ok = await asyncio.to_thread(read_artifact, state.settings, state.database, scan_id, path, limit=1)
    if ok is None:
        raise ScopeError("Không đọc được file này (không tồn tại hoặc ngoài thư mục scan).", "artifact_unavailable")
    slug = (await asyncio.to_thread(state.runner.review, scan_id))["slug"]
    return FileResponse(scan_root(state.settings, slug, scan_id) / path, filename=f"scan{scan_id}-{ok['name']}", media_type="text/plain")


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
    await runner.submit(scan_id, body.config)
    if body.automation_ack:
        await asyncio.to_thread(runner.record_ack, scan_id)
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
