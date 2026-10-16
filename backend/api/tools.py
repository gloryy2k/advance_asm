"""Tools & environment: what is installed, what each missing piece costs, and (on request) the versions found."""
import asyncio

from fastapi import APIRouter, Request

from backend.tools import DEPTHS, probe_versions, tool_inventory

router = APIRouter(prefix="/api/tools", tags=["tools"])


def _payload(request: Request):
    settings = request.app.state.settings
    templates = None
    store = getattr(request.app.state, "templates", None)
    if store is not None:
        templates = store.describe()
    rows = tool_inventory(settings, templates)
    import os
    import platform
    return {"tools": rows, "depths": list(DEPTHS),
            "runtime": {"os": platform.system(), "recon_supported": os.name == "posix"},
            "summary": {"ready": sum(r["state"] == "ready" for r in rows),
                        "missing_required": [r["id"] for r in rows if r["state"] != "ready" and r["required_for"]],
                        "missing_optional": [r["id"] for r in rows if r["state"] != "ready" and not r["required_for"] and r["kind"] != "framework"],
                        "missing_framework": [r["id"] for r in rows if r["state"] != "ready" and r["kind"] == "framework"]}}


@router.get("")
async def tools(request: Request):
    """Read-only: looks for files, never runs a tool or touches a target."""
    return await asyncio.to_thread(_payload, request)


@router.post("/check")
async def check(request: Request):
    """Deep check, only when the user asks: runs `<tool> -version` (update checks off, 8 s each) for tools that are present."""
    await asyncio.to_thread(probe_versions, request.app.state.settings)
    return await asyncio.to_thread(_payload, request)
