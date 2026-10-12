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
        assert client.post(f"/api/scans/{result.scan_id}/launch", json={}).status_code == 200
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
