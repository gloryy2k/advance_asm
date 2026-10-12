import json

from backend.asm.monitors import Monitors
from backend.jobs.ingest import Ingester
from backend.jobs.recon_orch import ReconOrchestrator
from backend.tests.p2_helpers import environment, write_output


def setup(settings):
    db, _, result = environment(settings, ["*.example.com"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    write_output(plan.commands[0].output, "subdomains/all.txt", "api.example.com\nevil.invalid\n")
    Ingester(settings, db).ingest(plan)
    return db, plan, Monitors(settings, db)


def test_tc_mn_1_2_findings_scoped_redacted_and_idempotent(settings):
    db, plan, monitors = setup(settings)
    write_output(plan.root, "monitors/takeover/dnsreaper.json", json.dumps([
        {"domain": "api.example.com", "service": "s3"}, {"domain": "evil.invalid", "service": "s3"}]))
    write_output(plan.root, "monitors/secret/trufflehog.jsonl", json.dumps(
        {"DetectorName": "AWS", "Verified": True, "Raw": "DO-NOT-STORE-SECRET"}) + "\n")
    write_output(plan.root, "monitors/secret/noseyparker.jsonl", json.dumps({"rule_name": "token"}) + "\ninvalid\n")
    write_output(plan.commands[0].output, "js/endpoints.txt", "https://api.example.com/v1\nhttps://evil.invalid/api\n/api/account\n")
    assert monitors.ingest(plan) == 5
    assert monitors.ingest(plan) == 5
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM finding")]
    assert len(rows) == 5
    assert "DO-NOT-STORE" not in json.dumps(rows)
    assert "evil.invalid" not in json.dumps(rows)
    assert next(r for r in rows if r["type"] == "takeover")["severity"] == "high"
    assert next(r for r in rows if r["name"] == "AWS")["severity"] == "high"
    assert next(r for r in rows if r["name"] == "token")["severity"] == "medium"
    assert next(r for r in rows if r["name"] == "/api/account")["asset_id"] is None


def test_tc_mn_3_missing_tools_and_passive(settings, monkeypatch):
    db, plan, monitors = setup(settings)
    monkeypatch.setattr(monitors, "available", lambda *names: False)
    assert monitors.commands(plan) == []
    assert monitors.ingest(plan) == 0
    monkeypatch.setattr(monitors, "available", lambda *names: True)
    plan.config.depth = "passive"
    assert monitors.commands(plan) == []


def test_monitor_commands_use_only_gated_inputs(settings, monkeypatch):
    db, plan, monitors = setup(settings)
    write_output(plan.commands[0].output, "urls/js_files.txt", "https://api.example.com/app.js\nhttps://evil.invalid/payload.js\n")
    monkeypatch.setattr(monitors, "available", lambda *names: True)
    commands = monitors.commands(plan)
    assert len(commands) == 2
    assert all(c.env["BBASM_NO_VERIFY"] == "1" for c in commands)
    assert (plan.root / "monitors/input/subdomains/all.txt").read_text().splitlines() == ["api.example.com"]
    assert (plan.root / "monitors/input/urls/js_files.txt").read_text().splitlines() == ["https://api.example.com/app.js"]
    assert commands[0].argv[1] == str(settings.tool_path("takeover_scanner.sh"))


def test_monitor_subjack_and_regex_outputs(settings):
    db, plan, monitors = setup(settings)
    write_output(plan.root, "monitors/takeover/subjack.txt", "[S3] api.example.com\ninvalid\n")
    write_output(plan.root, "monitors/secret/regex_hits.txt", "api_key=THIS_IS_A_SECRET_VALUE\n")
    assert monitors.ingest(plan) == 2
    with db.connect() as conn:
        assert "THIS_IS_A_SECRET_VALUE" not in json.dumps([dict(r) for r in conn.execute("SELECT * FROM finding")])


def test_secret_maps_unique_bundle_source_to_asset(settings):
    db, plan, monitors = setup(settings)
    write_output(plan.root, "monitors/input/urls/js_files.txt", "https://api.example.com/app.js\n")
    write_output(plan.root, "monitors/secret/trufflehog.jsonl", json.dumps({
        "DetectorName": "AWS", "SourceMetadata": {"Data": {"Filesystem": {
            "file": "/output/js_bundles/https___api.example.com_app.js.js"}}}}) + "\n")
    assert monitors.ingest(plan) == 1
    with db.connect() as conn:
        assert conn.execute("SELECT asset_id FROM finding").fetchone()[0] is not None
