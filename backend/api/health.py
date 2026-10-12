"""Read-only availability checks: never execute tools or contact targets."""

import shutil

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["health"])
EXECUTABLES = (
    "bash", "subfinder", "httpx", "dnsx", "nuclei", "katana", "gau",
    "amass", "ffuf", "nmap", "git", "bbscope", "trufflehog",
)
FRAMEWORK_FILES = (
    "recon_engine.sh", "scope_aggregator.sh", "scope_checker.py",
    "recon_adapter.py", "intel_engine.py", "takeover_scanner.sh", "secrets_hunter.sh",
)


class HealthResponse(BaseModel):
    ok: bool
    tools: dict[str, bool]


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    tools = {name: shutil.which(name, path=settings.tool_search_path()) is not None for name in EXECUTABLES}
    tools.update({name: settings.tool_path(name).is_file() for name in FRAMEWORK_FILES})
    return HealthResponse(ok=True, tools=tools)
