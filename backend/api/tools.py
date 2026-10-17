"""Tools & environment: what is installed, what each missing piece costs, and (on request) the versions found."""
import asyncio

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

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


class CustomTemplate(BaseModel):
    content: str = Field(min_length=10, max_length=300_000)


def _store(request: Request):
    return request.app.state.templates


@router.get("/templates")
async def templates(request: Request):
    return await asyncio.to_thread(_store(request).describe)


@router.post("/templates/update")
async def update_templates(request: Request):
    """Install or update the official nuclei templates now. One at a time; the old set is kept if it fails."""
    job = await asyncio.to_thread(_store(request).start_update)
    return {"job": job}


@router.post("/templates/custom")
async def import_template(body: CustomTemplate, request: Request):
    """Add one YAML template of your own (checked, never run here, never part of a scan unless you choose it in Review)."""
    return await asyncio.to_thread(_store(request).import_custom, body.content.encode("utf-8"))


@router.delete("/templates/custom/{template_id}")
async def delete_template(template_id: str, request: Request):
    await asyncio.to_thread(_store(request).delete_custom, template_id)
    return {"deleted": template_id}


@router.get("/templates/lookup")
async def lookup_templates(request: Request, tag: str = Query(..., min_length=1, max_length=64)):
    """Preview which installed templates carry a tag (what -as/-tags would draw from). Read-only, no target touched."""
    return await asyncio.to_thread(_store(request).lookup_by_tag, tag)
