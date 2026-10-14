from fastapi.testclient import TestClient

from backend.main import create_app
from backend.tests.p2_helpers import FakeEgress, FakeProcess, environment, stop_fake


def test_review_launch_replay_and_config_is_immutable_after_launch(settings):
    db, _, result = environment(settings)
    app = create_app(settings)

    async def factory(command):
        assert command.env["BB_THREADS"] == "13"
        return FakeProcess()

    app.state.runner.process_factory = factory
    app.state.runner.stopper = stop_fake
    app.state.runner.egress = FakeEgress()
    with TestClient(app) as client:
        body = client.get(f"/api/scans/{result.scan_id}/config").json()
        body["threads"] = 201
        assert client.post(f"/api/scans/{result.scan_id}/launch", json={"config": body}).status_code == 422
        body["threads"] = 13
        assert client.put(f"/api/scans/{result.scan_id}/config", json=body).status_code == 200
        assert client.post(f"/api/scans/{result.scan_id}/launch", json={"automation_ack": True}).status_code == 200
        with client.websocket_connect(f"/ws/scan/{result.scan_id}") as websocket:
            events = []
            while not events or events[-1]["type"] != "done":
                events.append(websocket.receive_json())
        assert any(item["type"] == "phase" for item in events)
        assert events[-1]["status"] == "done"
        with client.websocket_connect(f"/ws/scan/{result.scan_id}") as websocket:
            assert websocket.receive_json()["id"] == events[0]["id"]
        assert client.put(f"/api/scans/{result.scan_id}/config", json=body).status_code == 422
        assert client.post(f"/api/scans/{result.scan_id}/launch", json={}).status_code == 422


def test_f6_api_requires_ack_above_passive_but_not_for_passive(settings):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    settings.BBASM_DEFAULT_DEPTH = "light"
    with TestClient(create_app(settings)) as client:
        made = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["127.0.0.1"], "name": "ack"}).json()
        cfg = client.get(f"/api/scans/{made['scan_id']}/config").json()
        denied = client.post(f"/api/scans/{made['scan_id']}/launch", json={"config": cfg})
        assert denied.status_code == 422 and denied.json()["error"]["code"] == "ack_required"
        assert client.get(f"/api/scans/{made['scan_id']}").json()["status"] == "draft"  # nothing started
        auto = client.post("/api/scans", json={"input": "raw", "scope": ["127.0.0.1"], "depth": "strong"})
        assert auto.status_code == 422 and auto.json()["error"]["code"] == "ack_required"
        cfg["depth"] = "passive"
        cfg["skip_nuclei"] = cfg["skip_active_crawl"] = cfg["skip_nmap"] = True
        ok = client.post(f"/api/scans/{made['scan_id']}/launch", json={"config": cfg})
        assert ok.status_code in (200, 422) and (ok.status_code == 200 or ok.json()["error"]["code"] != "ack_required")
