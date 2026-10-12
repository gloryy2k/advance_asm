from fastapi.testclient import TestClient

from backend.api.health import EXECUTABLES, FRAMEWORK_FILES
from backend.main import create_app


def test_tc_hlt_1_mixed_availability(monkeypatch, settings):
    settings.tools_dir.mkdir(parents=True)
    settings.tool_path("recon_engine.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    monkeypatch.setattr(
        "backend.api.health.shutil.which",
        lambda name, **kwargs: f"/bin/{name}" if name in {"bash", "nuclei"} else None,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "tools": {**{name: name in {"bash", "nuclei"} for name in EXECUTABLES},
                  **{name: name == "recon_engine.sh" for name in FRAMEWORK_FILES}},
    }


def test_missing_path_and_framework_fail_soft(monkeypatch, settings):
    monkeypatch.setenv("PATH", "")
    # Empty *effective* search path, including Go/Homebrew additions.
    monkeypatch.setattr(type(settings), "tool_search_path", lambda self: "")
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/health").json()
    assert body["ok"] is True
    assert not any(body["tools"].values())
    assert not settings.BBASM_DATA.exists()
    assert not settings.BBASM_TARGETS.exists()


def test_health_uses_configured_layout(monkeypatch, settings):
    settings.BBASM_TOOLS_SUBDIR = "bughunter/tools"
    settings.tools_dir.mkdir(parents=True)
    for name in FRAMEWORK_FILES:
        settings.tool_path(name).touch()
    monkeypatch.setattr("backend.api.health.shutil.which", lambda name, **kwargs: None)
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/health").json()
    assert all(body["tools"][name] for name in FRAMEWORK_FILES)


def test_cors_only_allows_configured_origin(settings):
    with TestClient(create_app(settings)) as client:
        allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        denied = client.get("/api/health", headers={"Origin": "https://untrusted.invalid"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers


def test_health_and_runner_find_go_bin_tool(monkeypatch, settings, tmp_path):
    import os
    from backend.jobs.recon_orch import ReconOrchestrator, recon_env
    from backend.jobs.scope_resolver import default_config

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "")
    binary = tmp_path / "go" / "bin" / ("gau.exe" if os.name == "nt" else "gau")
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["tools"]["gau"] is True
    assert "gau" not in ReconOrchestrator(settings, None).missing_tools()
    assert recon_env(settings, default_config(settings, []), tmp_path)["PATH"] == settings.tool_search_path()
