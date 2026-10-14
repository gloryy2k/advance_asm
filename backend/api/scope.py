"""Scope resolve (creates the draft) and preview (pure parse, writes nothing)."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.jobs.scope_parse import parse_scope, summarize
from backend.jobs.scope_resolver import ScopeError, h1_handle
from backend.models import ResolveRequest, ResolveResponse

router = APIRouter(prefix="/api/scope", tags=["scope"])


class PreviewRequest(BaseModel):
    input: str = Field(min_length=1, max_length=2048)
    scope: list[str] = Field(default_factory=list, max_length=10000)
    scope_out: list[str] = Field(default_factory=list, max_length=10000)


@router.post("/resolve", response_model=ResolveResponse)
def resolve_scope(body: ResolveRequest, request: Request):
    request.app.state.database.migrate()
    result = request.app.state.scope_resolver.resolve(body)
    from backend.brief.generator import BriefGenerator
    BriefGenerator(request.app.state.settings, request.app.state.database).ensure_program(result.slug)
    return result


@router.post("/preview")
def preview_scope(body: PreviewRequest):
    """Explain how input will be understood. No database, file or network access."""
    if body.input.strip() == "raw":
        lines = parse_scope(body.scope, body.scope_out)
        summary = summarize(lines)
        ok = summary["errors"] == 0 and summary["effective_in"] > 0
        message = "" if ok else ("Có dòng lỗi; sửa trước khi tiếp tục" if summary["errors"] else
                                 "Mọi mục IN đều bị OUT loại; không còn gì để quét" if summary["in"] else "Chưa có mục IN hợp lệ")
        return {"mode": "raw", "ok": ok, "message": message, "summary": summary,
                "lines": [line.public() for line in lines]}
    try:
        return {"mode": "h1", "ok": True, "handle": h1_handle(body.input), "message": "", "lines": [],
                "summary": {"in": 0, "out": 0, "effective_in": 0, "errors": 0, "warnings": 0}}
    except ScopeError as exc:
        return {"mode": "h1", "ok": False, "handle": None, "message": str(exc), "lines": [],
                "summary": {"in": 0, "out": 0, "effective_in": 0, "errors": 1, "warnings": 0}}
