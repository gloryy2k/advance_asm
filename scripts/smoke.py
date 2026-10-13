"""Opt-in real API/scan smoke test. Run only against an authorized target."""
import argparse
from pathlib import Path
import time

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--target", default="example.com")
    parser.add_argument("--depth", choices=["passive", "light", "strong"], default="passive")
    parser.add_argument("--output", type=Path, default=Path("smoke-export.zip"))
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        print("Health:", health.json())
        response = client.post("/api/scope/resolve", json={"input": "raw", "scope": [args.target]})
        response.raise_for_status()
        resolved = response.json()
        config = resolved["config"]
        config.update(depth=args.depth, scan_timeout={"passive": 300, "light": 900, "strong": 2700}[args.depth],
                      skip_nmap=args.depth != "strong", skip_nuclei=args.depth == "passive",
                      skip_active_crawl=args.depth == "passive",
                      nuclei_severity={"passive": "", "light": "low,medium", "strong": "low,medium,high,critical"}[args.depth])
        scan_id, slug = resolved["scan_id"], resolved["slug"]
        print("Resolved scope; launching", scan_id, slug, config)
        started = time.monotonic()
        client.post(f"/api/scans/{scan_id}/launch", json={"config": config}).raise_for_status()
        while time.monotonic() - started < config["scan_timeout"] + 180:
            response = client.get(f"/api/scans/{scan_id}")
            response.raise_for_status()
            status = response.json()
            if status["status"] in {"done", "done_partial", "failed", "cancelled"}:
                break
            time.sleep(2)
        else:
            client.post(f"/api/scans/{scan_id}/cancel")
            raise SystemExit("Smoke deadline exceeded; cancel requested")
        print("Result:", status["status"], "seconds:", round(time.monotonic() - started, 2))
        if status["status"] not in {"done", "done_partial"}:
            raise SystemExit(status.get("error") or status["status"])
        with client.stream("GET", f"/api/programs/{slug}/export?include_recon=false") as response:
            response.raise_for_status()
            with args.output.open("wb") as stream:
                for chunk in response.iter_bytes(65536):
                    stream.write(chunk)
        print("ZIP:", args.output.resolve())


if __name__ == "__main__":
    main()
