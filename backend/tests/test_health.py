from fastapi.testclient import TestClient

from backend.api.health import EXECUTABLES, FRAMEWORK_FILES
from backend.main import create_app


def test_tc_hlt_1_mixed_availability(monkeypatch, settings):
    settings.tools_dir.mkdir(parents=True)
    settings.tool_path("recon_engine.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    monkeypatch.setattr(
        "backend.api.health.shutil.which",
        lambda name: f"/bin/{name}" if name in {"bash", "nuclei"} else None,
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
    monkeypatch.setattr("backend.api.health.shutil.which", lambda name: None)
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/health").json()
    assert all(body["tools"][name] for name in FRAMEWORK_FILES)


def test_cors_only_allows_configured_origin(settings):
    with TestClient(create_app(settings)) as client:
        allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        denied = client.get("/api/health", headers={"Origin": "https://untrusted.invalid"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers
