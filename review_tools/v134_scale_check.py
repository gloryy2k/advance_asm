"""Host QA only: API scan with large offline mock output and a held ingest for Cancel."""
import faulthandler
import json
import os
import tempfile
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.tests.p2_helpers import FakeEgress, FakeProcess, write_output


HOSTS = [f"h{i:03d}.qa.test" for i in range(750)]
URLS = [f"https://{host}/p{j}?id={j}" for host in HOSTS for j in range(17)]
assert len(URLS) == 12750


def output(label, obj):
    print(label, json.dumps(obj, ensure_ascii=True, default=str), flush=True)


with tempfile.TemporaryDirectory(prefix="bbasm-v134-") as temp:
    settings = Settings(_env_file=None, BBASM_DATA=Path(temp) / "data",
                        BBASM_TARGETS=Path(temp) / "targets",
                        BBASM_BBROOT=Path("/opt/claude-bug-bounty"),
                        BBASM_SKIP_HISTORICAL=True)
    app = create_app(settings)
    runner = app.state.runner

    async def mock_process(command):
        write_output(command.output, "subdomains/all.txt", "\n".join(HOSTS) + "\n")
        write_output(command.output, "urls/all.txt", "\n".join(URLS) + "\n")
        return FakeProcess()

    runner.process_factory = mock_process
    runner.egress = FakeEgress()

    with TestClient(app) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        def new_scan():
            draft = request("POST", "/api/scope/resolve", json={"input": "raw", "name": "qa-v134-scale", "scope": ["*.qa.test"]})
            scan_id = draft["scan_id"]
            config = request("GET", f"/api/scans/{scan_id}/config")
            config.update(depth="passive", threads=1, rate_limit=1, scan_timeout=120,
                          skip_historical=True, skip_nuclei=True, skip_active_crawl=True,
                          skip_takeover=True, skip_secrets=True)
            request("POST", f"/api/scans/{scan_id}/launch", json={"config": config, "automation_ack": False})
            return scan_id

        def poll(scan_id, *, until_terminal=True, entered=None):
            started = time.monotonic()
            rows = []
            while time.monotonic() - started < 180:
                t0 = time.monotonic()
                status = request("GET", f"/api/scans/{scan_id}")
                phases = request("GET", f"/api/scans/{scan_id}/phases")
                review = request("GET", f"/api/scans/{scan_id}/review")
                rows.append({"status": status["status"], "latency_s": round(time.monotonic() - t0, 3),
                             "phase_status": phases.get("status"), "review_status": review["scan"]["status"]})
                if until_terminal and status["status"] in {"done", "done_partial", "failed", "cancelled"}:
                    return status, rows
                if entered is not None and entered.is_set():
                    return status, rows
                time.sleep(max(0, 1 - (time.monotonic() - t0)))
            faulthandler.dump_traceback(all_threads=True)
            raise TimeoutError(f"scan {scan_id} stayed {rows[-1]['status']}")

        first = new_scan()
        first_row, first_polls = poll(first)
        first_stats = json.loads(first_row.get("stats_json") or "{}")
        first_stages = [e for e in runner.logs.replay(first) if e.get("type") == "stage"
                        and e.get("key") in {"ingest", "monitors", "diff", "rank", "brief"}]
        output("first", {"id": first, "status": first_row["status"], "error": first_row.get("error"),
                         "urls": first_stats.get("urls"), "assets": first_stats.get("subs"),
                         "polls": len(first_polls), "max_poll_latency_s": max(p["latency_s"] for p in first_polls),
                         "stage_events": [{k: e.get(k) for k in ("key", "status", "used_s")} for e in first_stages],
                         "last_event": runner.logs.replay(first)[-1]["type"]})

        real_ingest = runner.ingester.ingest
        entered = threading.Event()
        release = threading.Event()

        def held_ingest(plan):
            result = real_ingest(plan)
            entered.set()  # DB has the full 12,750-URL fixture; hold the ingest return.
            release.wait(30)
            return result

        runner.ingester.ingest = held_ingest
        second = new_scan()
        second_row, second_polls = poll(second, until_terminal=False, entered=entered)
        assert entered.is_set(), "ingest did not reach the held point"
        started = time.monotonic()
        response = client.post(f"/api/scans/{second}/cancel", timeout=15)
        cancel_s = time.monotonic() - started
        release.set()
        response.raise_for_status()
        terminal, after_polls = poll(second)
        events = runner.logs.replay(second)
        output("cancel", {"id": second, "cancel_response_s": round(cancel_s, 3),
                          "cancel_http": response.status_code, "status": terminal["status"],
                          "polls_before": len(second_polls), "polls_after": len(after_polls),
                          "max_poll_latency_s": max(p["latency_s"] for p in second_polls + after_polls),
                          "last_event": {k: events[-1].get(k) for k in ("type", "status")},
                          "last_stage": next((e.get("key") for e in reversed(events) if e.get("type") == "stage"), None)})
