"""U1: range assets, draft lifecycle, PROGRAM.md before first scan, pagination, brief caps."""

import os
import asyncio
from datetime import datetime, timedelta, timezone
import json

from fastapi.testclient import TestClient
import pytest

from backend.brief.generator import BriefGenerator
from backend.jobs.ingest import Ingester
from backend.jobs.recon_orch import ReconOrchestrator
from backend.jobs.scope_resolver import ScopeError
from backend.main import create_app
from backend.models import ResolveRequest
from backend.tests.p2_helpers import environment, write_output


def test_ux_cidr_is_one_range_asset_not_254_hosts(settings):
    # F5: recon enumerates every address of a CIDR; only addresses with evidence are assets.
    db, _, result = environment(settings, ["198.51.100.0/24", "203.0.113.7"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    output = plan.commands[0].output
    addresses = [f"198.51.100.{i}" for i in range(1, 255)] + ["203.0.113.7"]
    write_output(output, "subdomains/all.txt", "\n".join(addresses) + "\n")
    write_output(output, "live/urls.txt", "http://198.51.100.9\n")
    write_output(output, "live/httpx_full.txt", "http://198.51.100.9 [200] [10] [Router] [nginx]\n")
    stats = Ingester(settings, db).ingest(plan)
    with db.connect() as conn:
        hosts = {r["host"]: dict(r) for r in conn.execute("SELECT * FROM asset")}
    assert set(hosts) == {"198.51.100.0/24", "198.51.100.9", "203.0.113.7"}
    assert hosts["198.51.100.0/24"]["category"] == "cidr"
    assert "256 địa chỉ" in hosts["198.51.100.0/24"]["title"] and "1 có phản hồi" in hosts["198.51.100.0/24"]["title"]
    assert hosts["203.0.113.7"]["category"] == "ip"  # an explicitly scoped single IP is always an asset
    assert stats["collapsed_ips"] == 253


def test_range_row_gets_no_fresh_rank_bonus():
    from backend.asm.ranking import score_asset
    base = {"host": "198.51.100.0/24", "first_seen_scan": 3, "status_code": None}
    assert score_asset({**base, "category": "cidr"}, 3)[0] == 0
    assert score_asset({**base, "category": "ip"}, 3)[0] == 1.5


def prepared_with_cidr(settings, many=300):
    db, _, result = environment(settings, ["*.example.com", "10.0.0.0/24"])
    with db.connect() as conn, conn:
        scan = conn.execute("SELECT * FROM scan_run").fetchone()
        stats = json.loads(scan["stats_json"])
        stats["resolved_scope"][0]["instruction"] = "Không test /internal"
        conn.execute("UPDATE scan_run SET status='done',stats_json=?", (json.dumps(stats),))
        conn.execute("INSERT INTO asset(program_id,host,title,category,first_seen_scan,last_seen_scan,state,rank_score,rank_reasons_json) VALUES(?,?,?,?,?,?,'active',0,'[]')",
                     (scan["program_id"], "10.0.0.0/24", "256 địa chỉ", "cidr", scan["id"], scan["id"]))
        for i in range(many):
            conn.execute("INSERT INTO asset(program_id,host,category,first_seen_scan,last_seen_scan,state,rank_score,rank_reasons_json) VALUES(?,?,?,?,?,'active',?,?)",
                         (scan["program_id"], f"api{i:03}.example.com", "web", scan["id"], scan["id"], 7,
                          json.dumps(["api", "fresh"])))
    return db, result, BriefGenerator(settings, db)


def test_tc_br_7_brief_caps_new_assets_shows_reasons_ranges_and_instructions(settings):
    db, result, gen = prepared_with_cidr(settings)
    out = gen.generate(result.slug)
    text = (gen.target(result.slug) / "AGENT_BRIEF.md").read_text(encoding="utf-8")
    assert out["bytes"] < 12000
    fresh = text.split("## ASSET MỚI")[1].split("## SIGNALS")[0]
    assert fresh.count("\n- api") == 30 and "và 270 asset mới khác" in fresh
    assert "|Lý do|" in text and "| api, fresh |" in text.replace("|api, fresh|", "| api, fresh |")
    assert "10.0.0.0/24 (dải: 256 địa chỉ" in text
    assert "Assets: 300 (+1 dải)" in text
    assert "IN *.example.com: Không test /internal" in text
    assert "kiểm tra phân quyền/IDOR" in text  # hint derived from the host's own rank reasons


def test_tc_prg_5_program_md_exists_and_is_editable_before_first_scan(settings):
    with TestClient(create_app(settings)) as client:
        slug = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["example.com"]}).json()["slug"]
        text = client.get(f"/api/programs/{slug}/program").text
        assert "## Policy" in text and "<!-- user-editable -->" in text
        assert client.put(f"/api/programs/{slug}/program", json={"content": "Auth: test account A"}).status_code == 200
        assert "Auth: test account A" in client.get(f"/api/programs/{slug}/program").text
        denied = client.get(f"/api/programs/{slug}/brief")
        assert denied.status_code == 422 and denied.json()["error"]["code"] == "no_completed_scan"


@pytest.mark.skipif(os.name != "posix", reason="Launches recon: needs Linux/WSL2/Docker (native Windows is refused by design)")
def test_tc_lc_5_second_resolve_does_not_rewrite_scope_rules_until_launch(settings):
    from unittest.mock import Mock
    from backend.db import Database
    from backend.jobs.scope_resolver import ScopeResolver, classify
    db = Database(settings.BBASM_DATA / "bbasm.db")
    db.migrate()
    provider = Mock()
    provider.resolve.return_value = ([classify("a.acme.com")], {}, [])
    resolver = ScopeResolver(settings, db, provider)
    first = resolver.resolve(ResolveRequest(input="h1:acme"))
    provider.resolve.return_value = ([classify("b.acme.com")], {}, [])
    second = resolver.resolve(ResolveRequest(input="h1:acme"))
    assert second.slug == first.slug and second.scan_id != first.scan_id
    with db.connect() as conn:  # a schedule would still read the old, confirmed scope
        assert [r[0] for r in conn.execute("SELECT pattern FROM scope_rule")] == ["a.acme.com"]
        snapshot = json.loads(conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (second.scan_id,)).fetchone()[0])
        assert snapshot["resolved_scope"][0]["pattern"] == "b.acme.com"
    from backend.jobs.runner import JobRunner
    JobRunner(settings, db)._enqueue(second.scan_id, None)  # launching confirms the new scope
    with db.connect() as conn:
        assert [r[0] for r in conn.execute("SELECT pattern FROM scope_rule")] == ["b.acme.com"]


@pytest.mark.skipif(os.name != "posix", reason="Launches recon: needs Linux/WSL2/Docker (native Windows is refused by design)")
def test_launch_applies_reviewed_snapshot_to_scope_rules(settings):
    from backend.jobs.runner import JobRunner
    db, resolver, first = environment(settings, ["a.example.com"])
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET stats_json=? WHERE id=?", (json.dumps({"resolved_scope": [
            {"pattern": "b.example.com", "kind": "in", "asset_type": "domain", "category": "web", "instruction": ""}]}), first.scan_id))
    runner = JobRunner(settings, db)
    runner._enqueue(first.scan_id, None)
    with db.connect() as conn:
        assert [r[0] for r in conn.execute("SELECT pattern FROM scope_rule")] == ["b.example.com"]


@pytest.mark.skipif(os.name != "posix", reason="Launches recon: needs Linux/WSL2/Docker (native Windows is refused by design)")
def test_tc_lc_6_delete_draft_cleans_orphan_program_but_not_launched(settings):
    with TestClient(create_app(settings)) as client:
        one = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["a.example.com"]}).json()
        assert client.get("/api/programs").json() == []  # never launched → not a program yet
        drafts = client.get("/api/drafts").json()
        assert [d["id"] for d in drafts] == [one["scan_id"]] and drafts[0]["in"] == 1
        assert len(client.get("/api/programs?include_drafts=true").json()) == 1
        assert client.delete(f"/api/scans/{one['scan_id']}").status_code == 200
        assert client.get("/api/drafts").json() == [] and client.get("/api/programs?include_drafts=true").json() == []
        assert client.get(f"/api/scans/{one['scan_id']}").status_code == 422
        # a scan that ran cannot be deleted
        two = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["b.example.com"]}).json()
        client.app.state.runner._enqueue(two["scan_id"], None)
        denied = client.delete(f"/api/scans/{two['scan_id']}")
        assert denied.status_code == 422 and denied.json()["error"]["code"] == "invalid_state"


def test_old_drafts_are_purged_at_boot_fresh_ones_kept(settings):
    db, resolver, old = environment(settings, ["old.example.com"])
    fresh = resolver.resolve(ResolveRequest(input="raw", scope=["fresh.example.com"]))
    stale = (datetime.now(timezone.utc) - timedelta(days=9)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_config SET created_at=? WHERE scan_run_id=?", (stale, old.scan_id))
    from backend.jobs.runner import JobRunner
    assert JobRunner(settings, db).purge_drafts(7) == 1
    with db.connect() as conn:
        assert [r[0] for r in conn.execute("SELECT id FROM scan_run")] == [fresh.scan_id]
        assert conn.execute("SELECT count(*) FROM program").fetchone()[0] == 1


def test_pagination_totals_filters_and_summary(settings):
    db, result, gen = prepared_with_cidr(settings, many=60)
    with db.connect() as conn, conn:
        scan = conn.execute("SELECT * FROM scan_run").fetchone()
        for i in range(25):
            conn.execute("INSERT INTO diff_event(program_id,scan_run_id,entity,entity_ref,change,detail_json,created_at) VALUES(?,?,?,?,?,?,?)",
                         (scan["program_id"], scan["id"], "asset", f"h{i}", "new" if i < 20 else "gone", "{}", "t"))
        asset = conn.execute("SELECT id FROM asset LIMIT 1").fetchone()[0]
        for n, sev in enumerate(("low", "critical", "medium", "critical")):
            conn.execute("INSERT INTO finding(program_id,asset_id,type,severity,name,first_seen_scan,last_seen_scan) VALUES(?,?,?,?,?,?,?)",
                         (scan["program_id"], asset, "nuclei", sev, f"n-{n}-{sev}", scan["id"], scan["id"]))
    with TestClient(create_app(settings)) as client:
        base = f"/api/programs/{result.slug}"
        page = client.get(base + "/assets?limit=10&offset=50")
        assert len(page.json()) == 10 and page.headers["x-total-count"] == "61"
        assert client.get(base + "/assets?category=cidr").headers["x-total-count"] == "1"
        assert client.get(base + "/assets?q=api00").headers["x-total-count"] == "10"
        assert client.get(base + "/assets?q=_").headers["x-total-count"] == "0"  # '_' is literal, not a wildcard
        diff = client.get(base + "/diff?change=new&limit=5")
        assert len(diff.json()) == 5 and diff.headers["x-total-count"] == "20"
        findings = client.get(base + "/findings")
        assert [f["severity"] for f in findings.json()][:2] == ["critical", "critical"]
        summary = client.get(base + "/summary").json()
        assert summary["changes"] == {"new": 20, "changed": 0, "gone": 5}
        assert summary["findings_by_severity"]["critical"] == 2 and summary["assets_active"] == 61
        assert len(summary["top_surface"]) == 5 and all(a["category"] != "cidr" for a in summary["top_surface"])
        portfolio = client.get("/api/programs").json()[0]
        assert portfolio["latest_scan"]["status"] == "done" and portfolio["finding_count"] == 4


@pytest.mark.skipif(os.name != "posix", reason="Launches recon: needs Linux/WSL2/Docker (native Windows is refused by design)")
def test_review_payload_rescan_ack_and_program_name(settings):
    with TestClient(create_app(settings)) as client:
        made = client.post("/api/scope/resolve", json={
            "input": "raw", "name": "My Target!", "scope": ["*.example.com", "app.example.com:8443"],
            "scope_out": ["admin.example.com"], "policy_text": "Chỉ giờ hành chính"}).json()
        assert made["slug"] == "my-target"  # human name wins over raw-<hash>; unsafe chars are slugged
        review = client.get(f"/api/scans/{made['scan_id']}/review").json()
        assert review["slug"] == made["slug"] and review["scan"]["status"] == "draft"
        assert review["policy"]["user_text"] == "Chỉ giờ hành chính" and review["policy"]["text"] == ""
        assert any("port" in w for w in review["warnings"])  # parse warnings survive navigation to Review
        assert [e["pattern"] for e in review["scope"] if e["kind"] == "out"] == ["admin.example.com"]
        assert review["target_path"].endswith(made["slug"])
        config = client.get(f"/api/scans/{made['scan_id']}/config").json()
        assert client.post(f"/api/scans/{made['scan_id']}/launch", json={"config": config, "automation_ack": True}).status_code == 200
        after = client.get(f"/api/scans/{made['scan_id']}/review").json()
        assert after["automation_ack"]  # recorded for audit
        audit = (settings.BBASM_TARGETS / made["slug"] / "audit.jsonl").read_text()
        assert "automation_ack_by_user" in audit
        client.post(f"/api/scans/{made['scan_id']}/cancel")
        again = client.post(f"/api/programs/{made['slug']}/rescan").json()
        assert again["slug"] == made["slug"] and again["scan_id"] != made["scan_id"]
        rescoped = client.get(f"/api/scans/{again['scan_id']}/review").json()["scope"]
        assert {(e["pattern"], e["kind"]) for e in rescoped} == {
            ("*.example.com", "in"), ("app.example.com", "in"), ("admin.example.com", "out")}


def test_health_reports_h1_api_without_secret(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["h1_api"] is False
    configured = type(settings)(**{**settings.model_dump(), "H1_USER": "u", "H1_TOKEN": "tok-secret"}, _env_file=None)
    with TestClient(create_app(configured)) as client:
        response = client.get("/api/health")
    assert response.json()["h1_api"] is True and "tok-secret" not in response.text
