"""Local-only v1.1 host QA probe. Requires an isolated BBASM stack on 127.0.0.1:18765."""
import hashlib
import io
import json
import os
import time
import zipfile
from pathlib import Path

import httpx
from websockets.sync.client import connect

BASE = "http://127.0.0.1:18765"
C = httpx.Client(base_url=BASE, timeout=15)


def req(method, path, **kwargs):
    r = C.request(method, path, **kwargs)
    if r.status_code >= 400:
        raise AssertionError(f"{method} {path}: {r.status_code} {r.text[:300]}")
    return r


def done(scan_id, timeout=180):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        obj = req("GET", f"/api/scans/{scan_id}").json()
        if obj["status"] in {"done", "done_partial", "failed", "cancelled"}:
            return obj
        time.sleep(1)
    raise AssertionError(f"scan {scan_id} timed out")


def main():
    print("HEALTH", json.dumps(req("GET", "/api/health").json(), ensure_ascii=False))
    draft = req("POST", "/api/scope/resolve", json={"input": "raw", "name": "v11-ws", "scope": ["127.0.0.1"]}).json()
    with connect(f"ws://127.0.0.1:18765/ws/scan/{draft['scan_id']}", open_timeout=5) as ws:
        print("WS", ws.response.status_code)
    req("DELETE", f"/api/scans/{draft['scan_id']}")

    cases = ["#OUT", "# OUTT", "OUT:", "a.com, b.com", "10.0.0.5/24",
             "10.0.0.1-10.0.0.20", "https://*.x.com", "app.x.com:8443", "bad host!!"]
    for item in cases:
        out = req("POST", "/api/scope/preview", json={"input": "raw", "scope": [item]}).json()
        print("PREVIEW", repr(item), json.dumps(out, ensure_ascii=False)[:450])
    for item in ("https://hackerone.com/acme?type=team", "https://www.hackerone.com/acme",
                 "hackerone.com/acme", "acme"):
        out = req("POST", "/api/scope/preview", json={"input": item}).json()
        print("H1_HANDLE", repr(item), out.get("handle"), out.get("summary"))

    draft = req("POST", "/api/scope/resolve", json={"input": "raw", "name": "v11-local", "scope": ["127.0.0.1"]}).json()
    sid, slug = draft["scan_id"], draft["slug"]
    cfg = req("GET", f"/api/scans/{sid}/config").json()
    cfg["depth"] = "passive"
    cfg["scan_timeout"] = 300
    cfg["skip_nmap"] = cfg["skip_nuclei"] = cfg["skip_active_crawl"] = True
    req("POST", f"/api/scans/{sid}/launch", json={"config": cfg, "automation_ack": False})
    state = done(sid)
    print("SCAN", sid, slug, state["status"])
    assert state["status"] in {"done", "done_partial"}
    r = C.delete(f"/api/scans/{sid}")
    print("DELETE_STARTED", r.status_code, r.json().get("error", {}).get("code"))
    assert r.status_code == 422
    summary = req("GET", f"/api/programs/{slug}/summary").json()
    brief = req("GET", f"/api/programs/{slug}/brief").text
    program = req("GET", f"/api/programs/{slug}/program").text
    print("SUMMARY", summary["changes"], "BRIEF_BYTES", len(brief.encode()), "PROGRAM_POLICY", "## Policy" in program)
    assert len(brief.encode()) < 12000 and "## Policy" in program
    target = Path(os.environ["BBASM_QA_TARGETS"]) / slug
    for name in ("AGENT_BRIEF.md", "PROGRAM.md", ".scope", "audit.jsonl"):
        assert (target / name).exists(), name
    audit = (target / "audit.jsonl").read_text(encoding="utf-8")
    print("AUDIT", "scope_resolved" in audit, "scan_finished" in audit)
    assert "scope_resolved" in audit and "scan_finished" in audit

    for flag in ("true", "false"):
        blob = req("GET", f"/api/programs/{slug}/export?include_recon={flag}").content
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            names = z.namelist()
            manifest = [n for n in names if n.endswith("MANIFEST.json")]
            assert manifest
            json.loads(z.read(manifest[0]))
            has_recon = any("/recon/" in "/" + n for n in names)
            print("ZIP", flag, len(names), "RECON", has_recon, "FILES", names[:12])
            if flag == "false":
                assert not has_recon

    draft2 = req("POST", "/api/scope/resolve", json={"input": "raw", "name": "v11-delete", "scope": ["127.0.0.1"]}).json()
    req("DELETE", f"/api/scans/{draft2['scan_id']}")
    drafts = req("GET", "/api/drafts").json()
    programs = req("GET", "/api/programs?include_drafts=true").json()
    print("DELETE_DRAFT", draft2["scan_id"], all(x.get("id") != draft2["scan_id"] for x in drafts), all(x.get("slug") != draft2["slug"] for x in programs))

    again = req("POST", f"/api/programs/{slug}/rescan").json()
    cfg = req("GET", f"/api/scans/{again['scan_id']}/config").json()
    cfg["depth"] = "passive"
    cfg["scan_timeout"] = 300
    cfg["skip_nmap"] = cfg["skip_nuclei"] = cfg["skip_active_crawl"] = True
    req("POST", f"/api/scans/{again['scan_id']}/launch", json={"config": cfg, "automation_ack": False})
    second = done(again["scan_id"])
    diff = req("GET", f"/api/programs/{slug}/diff?limit=1&offset=0")
    assets = req("GET", f"/api/programs/{slug}/assets?limit=1&offset=0&q=127&category=ip")
    print("RESCAN", second["status"], "DIFF_TOTAL", diff.headers.get("x-total-count"), "ASSETS_TOTAL", assets.headers.get("x-total-count"))

    cidr = req("POST", "/api/scope/resolve", json={"input": "raw", "name": "v11-cidr", "scope": ["127.0.0.0/30"]}).json()
    cfg = req("GET", f"/api/scans/{cidr['scan_id']}/config").json()
    cfg["depth"] = "passive"
    cfg["scan_timeout"] = 300
    cfg["skip_nmap"] = cfg["skip_nuclei"] = cfg["skip_active_crawl"] = True
    req("POST", f"/api/scans/{cidr['scan_id']}/launch", json={"config": cfg, "automation_ack": False})
    cs = done(cidr["scan_id"])
    ca = req("GET", f"/api/programs/{cidr['slug']}/assets?limit=100").json()
    cb = req("GET", f"/api/programs/{cidr['slug']}/brief").text
    print("CIDR", cs["status"], [(a["host"], a["category"]) for a in ca], "NEW_LINES", sum("| NEW" in x for x in cb.splitlines()))
    assert len(ca) == 1 and ca[0]["category"] == "cidr"

    cancel = req("POST", "/api/scope/resolve", json={"input": "raw", "name": "v11-cancel", "scope": ["127.0.0.1"]}).json()
    cfg = req("GET", f"/api/scans/{cancel['scan_id']}/config").json()
    cfg["depth"] = "light"
    req("POST", f"/api/scans/{cancel['scan_id']}/launch", json={"config": cfg, "automation_ack": True})
    time.sleep(3)
    req("POST", f"/api/scans/{cancel['scan_id']}/cancel")
    print("CANCEL", done(cancel["scan_id"], 30)["status"])

    sha = {str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob("*") if p.is_file()}
    Path(os.environ["BBASM_QA_SNAPSHOT"]).write_text(json.dumps(sha, indent=2), encoding="utf-8")
    print("SNAPSHOT", len(sha), "files")


if __name__ == "__main__":
    main()
