"""Offline API test: manual policy across raw rescan; no scan launch."""
import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from backend.config import Settings
from backend.main import create_app

with tempfile.TemporaryDirectory(prefix="bbasm-policy-rescan-") as temp:
    settings = Settings(_env_file=None, BBASM_DATA=Path(temp) / "data",
                        BBASM_TARGETS=Path(temp) / "targets",
                        BBASM_BBROOT=Path("/opt/claude-bug-bounty"),
                        BBASM_SKIP_HISTORICAL=True)
    app = create_app(settings)
    with TestClient(app) as client:
        initial = client.post("/api/scope/resolve", json={
            "input": "raw", "name": "qa-policy-rescan", "scope": ["127.0.0.1"],
            "policy_text": "X-HackerOne-Research: tester is required.",
        })
        initial.raise_for_status()
        before = client.get("/api/programs/qa-policy-rescan").json()["policy"]
        rescan = client.post("/api/programs/qa-policy-rescan/rescan")
        rescan.raise_for_status()
        after = client.get("/api/programs/qa-policy-rescan").json()["policy"]
        review = client.get(f"/api/scans/{rescan.json()['scan_id']}/review").json()
        print(json.dumps({
            "before_manual_policy": bool(before.get("user_policy_text")),
            "after_manual_policy": bool(after.get("user_policy_text")),
            "rescan_review_hint": review["request_header_hints"],
            "rescan_review_user_text": bool(review["policy"]["user_text"]),
        }, ensure_ascii=True))
