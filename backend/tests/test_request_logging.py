import logging

from fastapi.testclient import TestClient

from backend.main import create_app


def test_request_log_redacts_query_and_structures_errors(settings, caplog):
    settings.BBASM_STATIC = settings.BBASM_DATA / "no-static"
    app = create_app(settings)

    @app.get("/api/test-error")
    def fail():
        raise RuntimeError("DO-NOT-LOG-THIS-SECRET")

    with caplog.at_level(logging.INFO, logger="bbasm.requests"), TestClient(app) as client:
        response = client.get("/api/health?token=DO-NOT-LOG-THIS-SECRET")
        assert response.headers["X-Request-ID"]
        response = client.get("/api/test-error")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
    assert '"event": "request"' in caplog.text
    assert "DO-NOT-LOG-THIS-SECRET" not in caplog.text
