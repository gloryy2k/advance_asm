"""End-to-end Passive/Light on the QA container's 127.0.0.1 fixture only."""
import json
import time
from pathlib import Path
import httpx

BASE = "http://127.0.0.1:18765"
NAME = "qa-v134-end2end-local"
OUT = Path("review_evidence/v134_fixcheck/local_flow.json")
client = httpx.Client(base_url=BASE, timeout=30, trust_env=False)
result = {"target": "127.0.0.1", "program": NAME, "scans": []}

def send(method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()

for depth in ("passive", "light"):
    draft = send("POST", "/api/scope/resolve", json={"input": "raw", "name": NAME,
        "scope": ["127.0.0.1"], "policy_text": "QA-owned localhost fixture; automated tests permitted."})
    scan_id = draft["scan_id"]
    config = draft["config"]
    config.update(depth=depth, threads=1, rate_limit=1, scan_timeout=120,
                  categories_enabled=["ip"], skip_historical=True,
                  skip_nmap=True, skip_nuclei=True, skip_active_crawl=True,
                  skip_ffuf=True, skip_takeover=True, skip_secrets=True)
    review = send("GET", f"/api/scans/{scan_id}/review")
    assert depth in review["launch_gate"]["allowed_depths"]
    send("POST", f"/api/scans/{scan_id}/launch", json={
        "config": config, "automation_ack": depth != "passive"})
    started = time.monotonic()
    while True:
        status = send("GET", f"/api/scans/{scan_id}")
        if status["status"] in {"done", "done_partial", "failed", "cancelled"}:
            break
        if time.monotonic() - started > 180:
            raise RuntimeError(f"scan {scan_id} still {status['status']} after 180 s")
        if int(time.monotonic() - started) % 15 == 0:
            print(f"{depth} #{scan_id}: {status['status']}", flush=True)
        time.sleep(1)
    phases = send("GET", f"/api/scans/{scan_id}/phases")
    summary = send("GET", f"/api/programs/{NAME}/summary")
    stats = json.loads(status.get("stats_json") or "{}")
    item = {"id": scan_id, "depth": depth, "status": status["status"],
            "error": status.get("error"), "elapsed_s": round(time.monotonic() - started, 1),
            "phase_statuses": {x["key"]: x["status"] for x in phases.get("phases", [])},
            "latest_completed": (summary.get("last_completed_scan") or {}).get("id"),
            "stats": {k: stats.get(k) for k in ("subs", "live", "urls", "findings", "baseline_scan_id")}}
    result["scans"].append(item)
    print(json.dumps(item, ensure_ascii=True), flush=True)
    assert status["status"] in {"done", "done_partial"}, item

diff = client.get(f"/api/programs/{NAME}/diff?limit=10")
diff.raise_for_status()
result["diff"] = {"total": int(diff.headers.get("x-total-count", "0")),
                  "first_rows": len(diff.json())}
result["summary"] = {"scan_id": send("GET", f"/api/programs/{NAME}/urls/summary")["scan_id"]}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"saved": str(OUT), "diff": result["diff"]}, ensure_ascii=True), flush=True)
