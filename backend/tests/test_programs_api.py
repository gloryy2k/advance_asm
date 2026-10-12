from fastapi.testclient import TestClient

from backend.main import create_app
from backend.tests.test_brief_export import prepared


def test_portfolio_surface_filters_and_schedule(settings):
    db, result, _ = prepared(settings)
    with TestClient(create_app(settings)) as client:
        base = f"/api/programs/{result.slug}"
        assert client.get("/api/programs").json()[0]["asset_count"] == 30
        assert client.get(base).json()["scans"][0]["status"] == "done"
        rows = client.get(base + "/surface?limit=10").json()
        assert len(rows) == 10 and all("reasons" in r for r in rows)
        assert len(client.get(base + "/assets?q=api29").json()) == 1
        assert client.get(base + "/assets?min_rank=8").json() == []
        assert client.get(base + "/diff").json() == []
        assert len(client.get(base + "/findings?type=takeover&severity=high").json()) == 2
        response = client.post(base + "/schedule", json={"interval": "6h", "depth": "light", "enabled": True})
        assert response.status_code == 200 and response.json()["next_run_at"]
        assert client.get(base).json()["schedule"]["enabled"] == 1
        assert client.post(base + "/schedule", json={"interval": "daily", "depth": "passive", "enabled": False}).status_code == 200
        assert client.get(base + "/surface?limit=0").status_code == 422
        assert client.get("/api/programs/no-such-program").status_code == 422


def test_auto_scan_requires_valid_depth_and_portfolio_empty(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/programs").json() == []
        for payload in ({"input": "raw", "scope": ["example.com"]}, {"input": "raw", "scope": ["example.com"], "depth": "deep"}):
            response = client.post("/api/scans", json=payload)
            assert response.status_code == 422
            assert "error" in response.json()
