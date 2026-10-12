"""P2 scan control endpoints; portfolio/query endpoints follow in P5."""

import asyncio

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

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


@router.post("/api/scans/{scan_id}/launch")
async def launch(scan_id: int, body: LaunchRequest, request: Request):
    await request.app.state.runner.submit(scan_id, body.config)
    return {"scan_id": scan_id, "status": "queued"}


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
