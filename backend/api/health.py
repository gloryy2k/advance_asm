"""Read-only availability checks: never execute tools or contact targets."""

import os
import platform
import shutil

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["health"])
EXECUTABLES = (
    "bash", "subfinder", "httpx", "nuclei", "katana", "gau",
    "amass", "ffuf", "nmap", "git", "bbscope", "trufflehog",
)
FRAMEWORK_FILES = (
    "recon_engine.sh", "scope_aggregator.sh", "scope_checker.py",
    "recon_adapter.py", "intel_engine.py", "takeover_scanner.sh", "secrets_hunter.sh",
)


# Tools each depth actually needs; a missing one is skipped fail-soft, so Review shows it.
DEPTH_TOOLS = {
    "passive": ["subfinder", "gau"],
    "light": ["subfinder", "gau", "httpx", "katana", "nuclei", "nuclei-templates"],
    "strong": ["subfinder", "gau", "httpx", "katana", "nuclei", "nuclei-templates", "nmap", "ffuf", "amass"],
}
# Nothing in a scan depends on these: a missing one is not a problem and is shown as "optional".
OPTIONAL_TOOLS = ("bbscope", "git", "trufflehog")


class HealthResponse(BaseModel):
    ok: bool
    tools: dict[str, bool]
    missing_by_depth: dict[str, list[str]] = {}
    h1_api: bool = False  # H1_USER/H1_TOKEN configured (never expose the values)
    runtime: dict = {}
    optional_tools: list[str] = []


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
    from backend.jobs.recon_orch import nuclei_templates_ready
    tools["nuclei-templates"] = tools.get("nuclei", False) and nuclei_templates_ready(settings)
    missing = {depth: [t for t in needed if not tools.get(t)] for depth, needed in DEPTH_TOOLS.items()}
    h1 = bool(settings.H1_USER.get_secret_value() and settings.H1_TOKEN.get_secret_value())
    supported = os.name == "posix"
    runtime = {"os": platform.system(), "recon_supported": supported,
               "reason": "" if supported else "Máy chủ chạy trên Windows gốc nên không chạy được recon (cần Linux, WSL2 hoặc Docker)."}
    return HealthResponse(ok=True, tools=tools, missing_by_depth=missing, h1_api=h1, runtime=runtime, optional_tools=list(OPTIONAL_TOOLS))
