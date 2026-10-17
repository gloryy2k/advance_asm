"""QA-1: inspect endpoint and Strong cap using only temporary settings/paths."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.jobs.runner import JobRunner
from backend.jobs.scope_resolver import ScopeError


def make_settings(root, **overrides):
    return Settings(
        _env_file=None,
        BBASM_BBROOT=root / "vendor",
        BBASM_DATA=root / "data",
        BBASM_TARGETS=root / "targets",
        BBASM_STATIC=root / "static",
        BBASM_UPDATE_TEMPLATES="0",
        BBASM_RECON_DISABLED=True,
        **overrides,
    )


with TemporaryDirectory() as directory:
    root = Path(directory)
    defaults = make_settings(root)
    with TestClient(create_app(defaults)) as client:
        first = client.get("/api/meta/tool-defaults")
    custom = make_settings(root, BBASM_NMAP_TIMEOUT=111, BBASM_FFUF_MAXTIME=222,
                           BBASM_NUCLEI_TIMEOUT=333, BBASM_DEEP_HOSTS=44)
    with TestClient(create_app(custom)) as client:
        second = client.get("/api/meta/tool-defaults")
    print("TOOL_DEFAULTS", json.dumps({"status": [first.status_code, second.status_code],
                                       "default": first.json(), "custom": second.json()}))

    example = Path(__file__).resolve().parent.parent / ".env.example"
    sample_cap = int(next(line.split("=", 1)[1] for line in example.read_text(encoding="utf-8").splitlines()
                          if line.startswith("BBASM_SCAN_TIMEOUT_STRONG=")))
    sample_settings = make_settings(root, BBASM_SCAN_TIMEOUT_STRONG=sample_cap)
    preset = SimpleNamespace(depth="strong", scan_timeout=7200, excluded_hosts=[])
    try:
        JobRunner._validate(SimpleNamespace(settings=sample_settings), preset)
        rejected = False
        reason = ""
    except ScopeError as exc:
        rejected = True
        reason = str(exc)
    print("STRONG_CAP", json.dumps({"code_default": defaults.scan_timeout("strong"),
                                    "example_env": sample_cap, "frontend_preset": 7200,
                                    "preset_rejected_with_example_env": rejected, "reason": reason}))
