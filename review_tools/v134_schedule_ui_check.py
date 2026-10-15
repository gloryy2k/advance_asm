"""Read-only target QA: isolated temporary DB, no scan, no external network."""
import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app

with tempfile.TemporaryDirectory(prefix="bbasm-schedule-ui-") as temp:
    settings = Settings(_env_file=None, BBASM_DATA=Path(temp) / "data",
                        BBASM_TARGETS=Path(temp) / "targets",
                        BBASM_BBROOT=Path("/opt/claude-bug-bounty"),
                        BBASM_SKIP_HISTORICAL=True)
    app = create_app(settings)
    with TestClient(app) as client:
        draft = client.post("/api/scope/resolve", json={
            "input": "raw", "name": "qa-schedule-header", "scope": ["127.0.0.1"],
            "policy_text": "Add X-HackerOne-Research: <username> to requests.",
        })
        draft.raise_for_status()
        saved = client.put("/api/programs/qa-schedule-header/request-headers", json={
            "headers": ["X-HackerOne-Research: local-tester"]})
        saved.raise_for_status()
        summary = client.get("/api/programs/qa-schedule-header/summary").json()
        # Exact body emitted by frontend Program.tsx; no scan is launched.
        schedule = client.post("/api/programs/qa-schedule-header/schedule", json={
            "interval": "weekly", "depth": "light", "enabled": True,
            "automation_ack": True})
        schedule.raise_for_status()
        scheduled_config = json.loads(schedule.json()["config_json"])
        assert "X-HackerOne-Research" in scheduled_config["request_headers"][0]
        missing = client.put("/api/programs/qa-schedule-header/request-headers", json={"headers": []})
        missing.raise_for_status()
        refused = client.post("/api/programs/qa-schedule-header/schedule", json={
            "interval": "weekly", "depth": "light", "enabled": True,
            "automation_ack": True})
        skipped = client.post("/api/programs/qa-schedule-header/schedule", json={
            "interval": "weekly", "depth": "light", "enabled": True,
            "automation_ack": True, "skipped_headers": ["X-HackerOne-Research"]})
        skipped.raise_for_status()
        skipped_config = json.loads(skipped.json()["config_json"])
        assert skipped_config["skipped_headers"] == ["X-HackerOne-Research"]
        print(json.dumps({
            "saved_header_names": [h.split(":", 1)[0] for h in summary["request_headers"]],
            "schedule_http": schedule.status_code,
            "schedule_header_names": [h.split(":", 1)[0] for h in scheduled_config["request_headers"]],
            "no_header_http": refused.status_code,
            "no_header_error": refused.json().get("error"),
            "skipped_http": skipped.status_code,
            "skipped_names": skipped_config["skipped_headers"],
        }, ensure_ascii=True))
