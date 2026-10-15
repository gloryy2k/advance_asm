"""Bounded Strong control-plane QA on one Wolt IN asset; never prints header values."""
import json
import os
import time
from pathlib import Path
import httpx

BASE = "http://127.0.0.1:18765"
OUT = Path("review_evidence/v134_fixcheck/wolt_strong.json")
if os.environ.get("BBASM_ALLOW_WOLT_STRONG") != "1":
    raise SystemExit("Explicitly set BBASM_ALLOW_WOLT_STRONG=1 before repeating this external-target scan")
client = httpx.Client(base_url=BASE, timeout=90, trust_env=False)

def send(method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()

before = send("GET", "/api/programs/wolt")
assert before["source"] == "h1"
assert not (before.get("schedule") or {}).get("enabled")
existing = {r["id"] for r in before["scans"]}
draft = send("POST", "/api/programs/wolt/rescan")
assert draft["slug"] == "wolt" and draft["scan_id"] not in existing
scan_id = draft["scan_id"]
review = send("GET", f"/api/scans/{scan_id}/review")
assert review["policy"]["source"] == "public_page"
assert "strong" in review["launch_gate"]["allowed_depths"]
assert any(x["pattern"] == "corporate.wolt.com" and x["kind"] == "in" for x in review["scope"])
config = send("GET", f"/api/scans/{scan_id}/config")
headers = config.get("request_headers") or []
assert [x.split(":", 1)[0] for x in headers] == ["X-HackerOne-Research"]
web = [x["pattern"] for x in review["scope"] if x["kind"] == "in" and x["category"] == "web"]
assert "corporate.wolt.com" in web
config.update(depth="strong", threads=1, rate_limit=1, scan_timeout=180,
              categories_enabled=["web"],
              excluded_hosts=[x for x in web if x != "corporate.wolt.com"],
              skip_historical=True, skip_takeover=True, skip_secrets=True,
              skip_active_crawl=True, skip_nmap=True, skip_ffuf=True, skip_nuclei=True)
plan = send("POST", "/api/meta/plan", json=config)
assert config["request_headers"] == headers
result = {"scan_id": scan_id, "source": review["policy"]["source"],
          "allowed_depths": review["launch_gate"]["allowed_depths"],
          "selected_host": "corporate.wolt.com",
          "excluded_web_hosts": len(config["excluded_hosts"]),
          "rate_limit": config["rate_limit"], "threads": config["threads"],
          "scan_timeout": config["scan_timeout"],
          "header_names": [x.split(":", 1)[0] for x in headers],
          "disabled_steps": ["historical", "takeover", "secrets", "crawl", "nmap", "ffuf", "nuclei"],
          "plan": [{"key": x.get("key"), "status": x.get("status")} for x in plan.get("phases", [])]}

send("POST", f"/api/scans/{scan_id}/launch", json={"config": config, "automation_ack": True})
started = time.monotonic()
last_print = 0
while True:
    status = send("GET", f"/api/scans/{scan_id}")
    elapsed = time.monotonic() - started
    if status["status"] in {"done", "done_partial", "failed", "cancelled"}:
        break
    if elapsed > 240:
        send("POST", f"/api/scans/{scan_id}/cancel")
        status = send("GET", f"/api/scans/{scan_id}")
        result["qa_cancelled_at_s"] = round(elapsed, 1)
        break
    if elapsed - last_print >= 20:
        print(f"Strong Wolt #{scan_id}: {status['status']} after {elapsed:.0f}s", flush=True)
        last_print = elapsed
    time.sleep(2)

summary = send("GET", "/api/programs/wolt/summary")
row = next(x for x in send("GET", "/api/programs/wolt")["scans"] if x["id"] == scan_id)
stats = row.get("stats") or json.loads(row.get("stats_json") or "{}")
phases = send("GET", f"/api/scans/{scan_id}/phases")
result.update({"status": status["status"], "error": status.get("error"),
               "elapsed_s": round(time.monotonic() - started, 1),
               "counts": {k: stats.get(k) for k in ("subs", "live", "urls", "findings", "baseline_scan_id")},
               "coverage": stats.get("coverage"), "diff": stats.get("diff"),
               "phases": [{"key": x.get("key"), "status": x.get("status"), "count": x.get("count")}
                          for x in phases.get("phases", [])],
               "summary_latest": (summary.get("latest_scan") or {}).get("id")})
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"saved": str(OUT), "scan_id": scan_id, "status": result["status"],
                  "elapsed_s": result["elapsed_s"], "counts": result["counts"]}, ensure_ascii=True), flush=True)
