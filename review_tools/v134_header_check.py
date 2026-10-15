"""Offline API gate QA; all scan processes are in-memory mocks."""
import json
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.tests.p2_helpers import FakeEgress, FakeProcess, write_output

POLICY = "Please add X-HackerOne-Research: <your username> to requests."

with tempfile.TemporaryDirectory(prefix="bbasm-v134-header-") as temp:
    settings = Settings(_env_file=None, BBASM_DATA=Path(temp) / "data",
                        BBASM_TARGETS=Path(temp) / "targets",
                        BBASM_BBROOT=Path("/opt/claude-bug-bounty"), BBASM_SKIP_HISTORICAL=True)
    app = create_app(settings)

    async def mock_process(command):
        write_output(command.output, "subdomains/all.txt", "127.0.0.1\n")
        return FakeProcess()

    app.state.runner.process_factory = mock_process
    app.state.runner.egress = FakeEgress()
    results = []

    with TestClient(app) as client:
        def scenario(depth, mode):
            draft = client.post("/api/scope/resolve", json={"input": "raw", "name": "qa-v134-header",
                                                           "scope": ["127.0.0.1"], "policy_text": POLICY})
            draft.raise_for_status()
            scan_id = draft.json()["scan_id"]
            config = client.get(f"/api/scans/{scan_id}/config").json()
            config.update(depth=depth, threads=1, rate_limit=1, scan_timeout=90,
                          skip_historical=True, skip_nmap=True, skip_nuclei=True,
                          skip_ffuf=True, skip_active_crawl=True, skip_takeover=True,
                          skip_secrets=True, request_headers=[] if mode != "header" else
                          ["X-HackerOne-Research: tester-local"],
                          skip_required_headers=(mode == "skip"))
            review = client.get(f"/api/scans/{scan_id}/review").json()
            response = client.post(f"/api/scans/{scan_id}/launch", json={"config": config,
                                                               "automation_ack": depth != "passive"})
            item = {"depth": depth, "mode": mode, "hints": review["request_header_hints"],
                    "http": response.status_code}
            if response.status_code != 200:
                item["body"] = response.json()
                item["status"] = client.get(f"/api/scans/{scan_id}").json()["status"]
            else:
                for _ in range(100):
                    row = client.get(f"/api/scans/{scan_id}").json()
                    if row["status"] in {"done", "done_partial", "failed", "cancelled"}:
                        break
                    time.sleep(0.05)
                item["status"] = row["status"]
            results.append(item)

        for depth in ("light", "strong"):
            for mode in ("none", "header", "skip"):
                scenario(depth, mode)
        scenario("passive", "none")

    print(json.dumps(results, ensure_ascii=True), flush=True)
