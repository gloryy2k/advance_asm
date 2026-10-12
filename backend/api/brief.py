from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from backend.brief.export import build_export
from backend.brief.generator import BriefGenerator
from backend.jobs.scope_resolver import ScopeError

router = APIRouter(prefix="/api/programs/{slug}", tags=["handoff"])


def generator(request):
    return BriefGenerator(request.app.state.settings, request.app.state.database)


@router.post("/brief")
def regenerate(slug: str, request: Request):
    return generator(request).generate(slug)


def read(slug, request, filename):
    gen = generator(request)
    gen.snapshot(slug)
    path = gen.target(slug) / filename
    if not path.is_file() or path.is_symlink():
        raise ScopeError(f"{filename} unavailable")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown")


@router.get("/brief")
def brief(slug: str, request: Request):
    return read(slug, request, "AGENT_BRIEF.md")


@router.get("/program")
def program(slug: str, request: Request):
    return read(slug, request, "PROGRAM.md")


class ProgramEdit(BaseModel):
    content: str = Field(max_length=100000)


@router.put("/program")
def edit_program(slug: str, body: ProgramEdit, request: Request):
    generator(request).update_program(slug, body.content)
    return {"saved": True}


@router.get("/export")
def export(slug: str, request: Request, include_recon: bool = True):
    path, filename = build_export(generator(request), slug, include_recon)
    return FileResponse(path, media_type="application/zip", filename=filename,
                        background=BackgroundTask(path.unlink, missing_ok=True))
