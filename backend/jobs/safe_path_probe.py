"""Bounded, request-by-request verification for hosts with OUT URL paths.

General crawlers and template engines cannot promise path exclusions. This worker
only requests exact, already known URLs approved by the scan's ScopeGate; it does
not follow redirects, discover links, execute JavaScript or fetch response bodies.
"""

import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

import httpx


_SAFE_PATH = re.compile(r"/[A-Za-z0-9_./~-]*\Z")


def simple_candidate(url: str, host: str) -> bool:
    """Reject URL encodings and ambiguous paths before an active request."""
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError:
        return False
    path = parsed.path or "/"
    return (parsed.scheme in {"http", "https"} and parsed.hostname == host
            and parsed.username is None and parsed.password is None
            and not parsed.query and not parsed.fragment and path != "/"
            and bool(_SAFE_PATH.fullmatch(path)) and "//" not in path
            and all(part not in {".", ".."} for part in path.split("/")))


def _headers() -> dict[str, str]:
    headers = {}
    for line in os.environ.get("BBHUNT_AUTH_HEADERS", "").splitlines():
        name, sep, value = line.partition(":")
        if sep and name.strip() and value.strip():
            headers[name.strip()] = value.strip()
    return headers


def run(input_path: Path, output: Path) -> int:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    host = data["host"]
    deny_paths = tuple(data["deny_paths"])
    urls = data["urls"][:50]
    rate = max(1, min(20, int(data["rate_limit"])))
    output.mkdir(parents=True, exist_ok=True)
    target = output / "urls" / "path_probe.txt"
    evidence = output / "urls" / "path_probe.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with httpx.Client(headers=_headers(), timeout=5.0, follow_redirects=False, trust_env=False) as client, \
            target.open("w", encoding="utf-8") as found, evidence.open("w", encoding="utf-8") as details:
        for url in urls:
            if not simple_candidate(url, host):
                continue
            path = urlsplit(url).path.lower()
            if any(path == rule or path.startswith(rule + "/") for rule in deny_paths):
                continue
            try:
                with client.stream("GET", url) as response:
                    found.write(url + "\n")
                    details.write(json.dumps({"url": url, "status_code": response.status_code}) + "\n")
                    count += 1
            except httpx.HTTPError:
                pass
            time.sleep(1 / rate)
    print(f"[✓] Safe path verification: {count} URLs answered; redirects not followed")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(Path(sys.argv[1]), Path(sys.argv[2])))
