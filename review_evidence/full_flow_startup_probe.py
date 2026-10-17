"""AUDIT full-flow: one stale scheduled config should not take down the dashboard."""
import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.models import ScanConfig


with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    common = dict(_env_file=None, BBASM_DATA=root / "data", BBASM_TARGETS=root / "targets",
                  BBASM_BBROOT=Path("vendor/claude-bug-bounty").resolve(),
                  BBASM_RECON_DISABLED=True, BBASM_UPDATE_TEMPLATES="0")
    original = Settings(**common, BBASM_SCAN_TIMEOUT_STRONG=7200)
    with TestClient(create_app(original)) as client:
        made = client.post("/api/scope/resolve", json={"input": "raw", "name": "qa-schedule", "scope": ["127.0.0.1"]}).json()
        config = client.get(f"/api/scans/{made['scan_id']}/config").json()
        config = ScanConfig.model_validate({**config, "depth": "strong", "scan_timeout": 7200})
        db = client.app.state.database
        with db.connect() as conn, conn:
            program_id = conn.execute("SELECT id FROM program WHERE slug='qa-schedule'").fetchone()[0]
            conn.execute("INSERT INTO schedule(program_id,interval,depth,enabled,config_json,next_run_at,created_at) "
                         "VALUES(?,'daily','strong',1,?,'2026-10-20T00:00:00+00:00','2026-10-18T00:00:00Z')",
                         (program_id, config.model_dump_json()))
    reduced = Settings(**common, BBASM_SCAN_TIMEOUT_STRONG=2700)
    error = None
    try:
        with TestClient(create_app(reduced)) as client:
            client.get("/api/health")
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)[:120]}
    print("STALE_SCHEDULE_BOOT", json.dumps({"startup_error": error}))
