import json

from backend.jobs.ingest import Ingester
from backend.jobs.recon_orch import ReconOrchestrator
from backend.models import ResolveRequest
from backend.tests.p2_helpers import environment, write_output


def test_tc_in_1_2_nested_output_idempotent_and_scope_filtered(settings):
    db, resolver, result = environment(settings, ["*.example.com"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    output = plan.commands[0].output
    write_output(output, "subdomains/all.txt", "api.example.com\nwww.example.com\nevil.com\n")
    write_output(output, "live/urls.txt", "https://api.example.com\n")
    write_output(output, "live/httpx_full.txt", "https://api.example.com [200] [123] [API console] [nginx,GraphQL]\n")
    write_output(output, "urls/all.txt", "https://api.example.com/v1\nhttps://evil.com\n")
    finding = {"template-id": "test", "matched-at": "https://api.example.com/v1", "info": {"severity": "medium", "name": "Test"}}
    write_output(output, "nuclei/findings.jsonl", json.dumps(finding) + "\ninvalid\n" + json.dumps(finding) + "\n")
    ingest = Ingester(settings, db)
    first = ingest.ingest(plan)
    assert first == ingest.ingest(plan)
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM asset").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM url").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM finding").fetchone()[0] == 1
        api = conn.execute("SELECT * FROM asset WHERE host='api.example.com'").fetchone()
        assert api["status_code"] == 200
        assert api["title"] == "API console"
        assert json.loads(api["tech_json"]) == ["nginx", "GraphQL"]
    second = resolver.resolve(ResolveRequest(input="raw", scope=["*.example.com"]))
    next_plan = ReconOrchestrator(settings, db).build(second.scan_id)
    write_output(next_plan.commands[0].output, "subdomains/all.txt", "api.example.com\n")
    ingest.ingest(next_plan)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM asset WHERE host='api.example.com'").fetchone()
        assert row["first_seen_scan"] == result.scan_id
        assert row["last_seen_scan"] == second.scan_id


def test_source_secret_ingest_idempotent_without_storing_raw_keys(settings):
    db, _, result = environment(settings, ["repo:https://github.com/acme/repo"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    write_output(plan.commands[0].output, "trufflehog.jsonl", json.dumps({"DetectorName": "AWS", "Verified": False, "Raw": "do-not-store"}) + "\n")
    ingest = Ingester(settings, db)
    ingest.ingest(plan)
    ingest.ingest(plan)
    with db.connect() as conn:
        assert conn.execute("SELECT category FROM asset").fetchone()[0] == "source_code"
        row = conn.execute("SELECT * FROM finding").fetchone()
        assert row["severity"] == "medium"
        assert "do-not-store" not in row["detail_json"]
        assert conn.execute("SELECT count(*) FROM finding").fetchone()[0] == 1
