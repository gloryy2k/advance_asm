"""AUDIT full-flow: URL selectors vs asset/finding selectors on disposable localhost data."""
import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app


with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    settings = Settings(_env_file=None, BBASM_DATA=root / "data", BBASM_TARGETS=root / "targets",
                        BBASM_BBROOT=Path("vendor/claude-bug-bounty").resolve(),
                        BBASM_RECON_DISABLED=True, BBASM_UPDATE_TEMPLATES="0")
    with TestClient(create_app(settings)) as client:
        a = client.post("/api/scope/resolve", json={"input": "raw", "name": "qa-a", "scope": ["127.0.0.1"]}).json()
        b = client.post("/api/scope/resolve", json={"input": "raw", "name": "qa-b", "scope": ["127.0.0.2"]}).json()
        db = client.app.state.database
        with db.connect() as conn, conn:
            aid = conn.execute("SELECT id FROM program WHERE slug='qa-a'").fetchone()[0]
            conn.execute("UPDATE scan_run SET status='done' WHERE id IN (?,?)", (a["scan_id"], b["scan_id"]))
            draft = conn.execute("INSERT INTO scan_run(program_id,depth,status) VALUES(?,'light','draft')", (aid,)).lastrowid
            conn.execute("INSERT INTO url(program_id,url,source,first_seen_scan,last_seen_scan,score,tags_json) "
                         "VALUES(?,'http://127.0.0.1/a','gau',?,?,1,'[]')", (aid, a["scan_id"], a["scan_id"]))
        base = "/api/programs/qa-a"
        checks = {}
        for label, scan_id in (("foreign", b["scan_id"]), ("draft", draft), ("missing", 999999)):
            scan = str(scan_id)
            urls = client.get(base + "/urls?scan=" + scan)
            summary = client.get(base + "/urls/summary?scan=" + scan)
            tree = client.get(base + "/urls/tree?scan=" + scan)
            exported = client.get(base + "/urls/export?scan=" + scan)
            assets = client.get(base + "/assets?scan=" + scan)
            checks[label] = {
                "selected_id": scan_id,
                "urls": {"status": urls.status_code, "total": urls.headers.get("x-total-count")},
                "summary": {"status": summary.status_code, "scan_id": summary.json().get("scan_id")},
                "tree": {"status": tree.status_code, "scan_id": tree.json().get("scan_id")},
                "export": {"status": exported.status_code, "contains_prior_url": "http://127.0.0.1/a" in exported.text},
                "assets_status": assets.status_code,
            }
        print("URL_SELECTOR", json.dumps(checks, sort_keys=True))
