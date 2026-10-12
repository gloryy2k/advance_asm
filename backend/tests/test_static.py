from fastapi.testclient import TestClient

from backend.main import create_app


def test_static_dashboard_keeps_api_routes(settings, tmp_path):
    settings.BBASM_STATIC = tmp_path / "static"
    settings.BBASM_STATIC.mkdir()
    (settings.BBASM_STATIC / "index.html").write_text("<h1>BBASM dashboard</h1>", encoding="utf-8")
    with TestClient(create_app(settings)) as client:
        assert "BBASM dashboard" in client.get("/").text
        assert client.get("/api/health").json()["ok"] is True
