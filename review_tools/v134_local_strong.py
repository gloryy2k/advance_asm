"""Exercise Strong's nmap phase against 127.0.0.1 only; all other active extras off."""
import json
import time
from pathlib import Path
import httpx

client = httpx.Client(base_url="http://127.0.0.1:18765", timeout=30, trust_env=False)

def send(method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()

draft = send("POST", "/api/scope/resolve", json={"input": "raw",
    "name": "qa-v134-end2end-local", "scope": ["127.0.0.1"],
    "policy_text": "QA-owned localhost fixture; automated tests permitted."})
scan_id = draft["scan_id"]
config = draft["config"]
config.update(depth="strong", threads=1, rate_limit=1, scan_timeout=180,
              categories_enabled=["ip"], skip_historical=True,
              skip_nmap=False, skip_nuclei=True, skip_active_crawl=True,
              skip_ffuf=True, skip_takeover=True, skip_secrets=True)
send("POST", f"/api/scans/{scan_id}/launch", json={"config": config, "automation_ack": True})
started = time.monotonic()
while True:
    status = send("GET", f"/api/scans/{scan_id}")
    if status["status"] in {"done", "done_partial", "failed", "cancelled"}:
        break
    if time.monotonic() - started > 220:
        send("POST", f"/api/scans/{scan_id}/cancel")
        status = send("GET", f"/api/scans/{scan_id}")
        break
    time.sleep(2)
phases = send("GET", f"/api/scans/{scan_id}/phases")
row = next(x for x in send("GET", "/api/programs/qa-v134-end2end-local")["scans"] if x["id"] == scan_id)
stats = row.get("stats") or json.loads(row.get("stats_json") or "{}")
result = {"scan_id": scan_id, "target": "127.0.0.1", "depth": "strong",
          "status": status["status"], "error": status.get("error"),
          "elapsed_s": round(time.monotonic() - started, 1),
          "counts": {k: stats.get(k) for k in ("subs", "live", "urls", "findings", "baseline_scan_id")},
          "phases": [{"key": x["key"], "status": x["status"], "count": x.get("count")}
                     for x in phases.get("phases", [])]}
out = Path("review_evidence/v134_fixcheck/local_strong.json")
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=True), flush=True)
