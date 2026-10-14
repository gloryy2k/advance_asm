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


# Tools each depth actually needs; a missing one is skipped fail-soft, so Review shows it.
DEPTH_TOOLS = {
    "passive": ["subfinder", "gau"],
    "light": ["subfinder", "gau", "httpx", "dnsx", "katana", "nuclei"],
    "strong": ["subfinder", "gau", "httpx", "dnsx", "katana", "nuclei", "nmap", "ffuf", "amass"],
}


class HealthResponse(BaseModel):
    ok: bool
    tools: dict[str, bool]
    missing_by_depth: dict[str, list[str]] = {}


def is_projectdiscovery_httpx(path: str) -> bool:
    """`httpx` on PATH is often the unrelated Python CLI; it is a script, the Go tool is a binary.

    Read-only on purpose: sniff the first bytes instead of executing the tool.
    """
    try:
        with open(path, "rb") as stream:
            return not stream.read(2) == b"#!"
    except OSError:
        return False


def tool_ready(name: str, search_path: str) -> bool:
    found = shutil.which(name, path=search_path)
    if found is None:
        return False
    return is_projectdiscovery_httpx(found) if name == "httpx" else True


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    tools = {name: tool_ready(name, settings.tool_search_path()) for name in EXECUTABLES}
    tools.update({name: settings.tool_path(name).is_file() for name in FRAMEWORK_FILES})
    missing = {depth: [t for t in needed if not tools.get(t)] for depth, needed in DEPTH_TOOLS.items()}
    return HealthResponse(ok=True, tools=tools, missing_by_depth=missing)
