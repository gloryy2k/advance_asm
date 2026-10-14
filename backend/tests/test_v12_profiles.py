"""V2: user profiles, per-scan options, and that every option really changes what happens."""

import os
import json

from fastapi.testclient import TestClient
import pytest

from backend.brief.generator import BriefGenerator
from backend.jobs.ingest import Ingester
from backend.jobs.recon_orch import ReconOrchestrator, recon_env
from backend.main import create_app
from backend.models import ScanConfig
from backend.tests.p2_helpers import environment, write_output
from backend.tests.test_v12_urls import ingest_fixture


def cfg(**over):
    base = dict(depth="light", threads=50, rate_limit=150, scan_timeout=900, nuclei_severity="low,medium", skip_nmap=True,
                skip_nuclei=False, skip_active_crawl=False, categories_enabled=["web"])
    return ScanConfig(**{**base, **over})


def test_old_config_without_new_fields_is_still_valid_and_defaults_are_safe():
    c = cfg()
    assert (c.skip_ffuf, c.skip_historical, c.skip_takeover, c.skip_secrets) == (False,) * 4
    assert (c.max_js_files, c.brief_budget_kb, c.brief_top_assets, c.brief_top_urls) == (100, 12, 25, 12)


@pytest.mark.parametrize("bad", [dict(max_js_files=101), dict(brief_budget_kb=13), dict(brief_budget_kb=3), dict(brief_top_urls=31),
                                 dict(url_exclude_patterns=["internal"]), dict(url_exclude_patterns=["/a b"]), dict(url_exclude_patterns=["/x;rm -rf"]),
                                 dict(url_exclude_patterns=["/a"] * 101)])
def test_option_bounds_are_enforced(bad):
    with pytest.raises(Exception):
        cfg(**bad)


def test_options_round_trip_through_the_database_and_the_orchestrator(settings):
    db, resolver, result = environment(settings, ["example.com"])
    with TestClient(create_app(settings)) as client:
        mine = {**client.get(f"/api/scans/{result.scan_id}/config").json(), "skip_ffuf": True, "skip_historical": True, "skip_takeover": True,
                "skip_secrets": True, "max_js_files": 7, "url_exclude_patterns": ["/internal/*"], "brief_budget_kb": 6, "brief_top_assets": 10, "brief_top_urls": 3}
        saved = client.put(f"/api/scans/{result.scan_id}/config", json=mine).json()
        assert saved["max_js_files"] == 7 and saved["url_exclude_patterns"] == ["/internal/*"]
        assert client.get(f"/api/scans/{result.scan_id}/config").json() == saved
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    assert plan.config.skip_secrets and plan.config.brief_budget_kb == 6
    env = recon_env(settings, ScanConfig(**{**saved}), plan.root)
    assert env["BBASM_SKIP_HISTORICAL"] == "1"
    strong = recon_env(settings, ScanConfig(**{**saved, "depth": "strong", "skip_ffuf": False, "scan_timeout": 900}), plan.root)
    assert strong["BBASM_SKIP_FFUF"] == "0"
    assert recon_env(settings, ScanConfig(**{**saved, "depth": "strong", "scan_timeout": 900}), plan.root)["BBASM_SKIP_FFUF"] == "1"


def test_url_exclude_patterns_drop_urls_and_are_counted(settings):
    db, _, result = environment(settings, ["vuihoc.vn"])
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_config SET options_json=?", (json.dumps({"url_exclude_patterns": ["/tin/*", "/INTERNAL/*"]}),))
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    out = plan.commands[0].output
    write_output(out, "subdomains/all.txt", "vuihoc.vn\n")
    write_output(out, "urls/all.txt", "https://vuihoc.vn/tin/a\nhttps://vuihoc.vn/internal/x\nhttps://vuihoc.vn/api/v1/ok\n")
    stats = Ingester(settings, db).ingest(plan)
    assert stats["urls"] == 1 and stats["url_funnel"]["excluded_by_rule"] == 2
    with db.connect() as conn:
        assert [r[0] for r in conn.execute("SELECT url FROM url")] == ["https://vuihoc.vn/api/v1/ok"]


def test_monitors_honour_skip_and_js_cap(settings, monkeypatch):
    from backend.asm.monitors import Monitors
    db, _, result = environment(settings, ["vuihoc.vn"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    write_output(plan.commands[0].output, "subdomains/all.txt", "vuihoc.vn\n")
    write_output(plan.commands[0].output, "urls/js_files.txt", "\n".join(f"https://vuihoc.vn/a{i}.js" for i in range(30)) + "\n")
    monitors = Monitors(settings, db)
    monkeypatch.setattr(monitors, "available", lambda *names: True)
    plan.config = plan.config.model_copy(update={"depth": "light", "max_js_files": 5})
    commands = {c.category: c for c in monitors.commands(plan)}
    assert set(commands) == {"takeover", "secret"}
    secret_input = (commands["secret"].output.parent / "input" / "urls/js_files.txt").read_text().split()
    assert len(secret_input) == 5
    plan.config = plan.config.model_copy(update={"skip_takeover": True, "skip_secrets": True})
    assert monitors.commands(plan) == []


def test_brief_follows_the_users_budget_and_counts(settings):
    db, result, stats = ingest_fixture(settings)
    with db.connect() as conn, conn:
        old = json.loads(conn.execute("SELECT stats_json FROM scan_run").fetchone()[0])
        conn.execute("UPDATE scan_run SET status='done',stats_json=?", (json.dumps({**old, **{k: v for k, v in stats.items() if k != "observations"}}),))
        conn.execute("UPDATE scan_config SET options_json=?", (json.dumps({"brief_top_urls": 0, "brief_top_assets": 5, "brief_budget_kb": 4}),))
    out = BriefGenerator(settings, db).generate(result.slug)
    text = (BriefGenerator(settings, db).target(result.slug) / "AGENT_BRIEF.md").read_text(encoding="utf-8")
    assert out["bytes"] < 4000
    assert "api/v1/users" not in text.split("## ENDPOINT ĐÁNG XEM")[1].split("## ASSET MỚI")[0]


def test_tc_pr_profiles_crud_validation_and_builtins(settings):
    with TestClient(create_app(settings)) as client:
        listing = client.get("/api/profiles").json()
        assert [p["name"] for p in listing["builtin"]] == ["Passive", "Light", "Strong"] and listing["custom"] == []
        light = next(p for p in listing["builtin"] if p["id"] == "builtin:light")["config"]
        assert light["nuclei_severity"] == "low,medium" and light["skip_nmap"] is True and light["scan_timeout"] == 900
        made = client.post("/api/profiles", json={"name": "Nhanh & rộng", "description": "nhiều luồng", "based_on": "light",
                                                  "config": {"threads": 120, "rate_limit": 400, "skip_nuclei": True, "url_exclude_patterns": ["/internal/*"]}})
        assert made.status_code == 200
        profile = made.json()
        assert profile["config"]["threads"] == 120 and profile["config"]["nuclei_severity"] == "low,medium"  # preset fills the rest
        assert client.post("/api/profiles", json={"name": "Nhanh & rộng", "config": {}}).json()["error"]["code"] == "profile_exists"
        assert client.post("/api/profiles", json={"name": "light", "config": {}}).json()["error"]["code"] == "invalid_profile"  # name of a preset
        for bad in ({"threads": 999}, {"rate_limit": 0}, {"depth": "ultra"}, {"categories_enabled": ["web"]}, {"scan_timeout": 99999}, {"evil": 1}, {"skip_nmap": "x"}):
            denied = client.post("/api/profiles", json={"name": "x", "config": bad})
            assert denied.status_code == 422 and denied.json()["error"]["code"] in {"invalid_profile", "validation_error"}, bad
        updated = client.put(f"/api/profiles/{profile['id']}", json={"name": "Nhanh", "config": {"threads": 10}}).json()
        assert updated["name"] == "Nhanh" and updated["config"]["threads"] == 10
        copy = client.post(f"/api/profiles/{profile['id']}/duplicate").json()
        assert copy["name"] == "Nhanh (bản sao)" and copy["id"] != profile["id"]
        assert len(client.get("/api/profiles").json()["custom"]) == 2
        assert client.delete(f"/api/profiles/{copy['id']}").status_code == 200
        assert client.delete(f"/api/profiles/{copy['id']}").json()["error"]["code"] == "profile_not_found"


@pytest.mark.skipif(os.name != "posix", reason="Launches recon: needs Linux/WSL2/Docker (native Windows is refused by design)")
def test_tc_pr_default_profile_seeds_new_drafts_but_keeps_their_scope(settings):
    with TestClient(create_app(settings)) as client:
        first = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["a.example.com", "10.0.0.0/24"]}).json()
        client.app.state.runner._enqueue(first["scan_id"], None)  # launching makes it a program
        profile = client.post("/api/profiles", json={"name": "Của tôi", "config": {"depth": "passive", "threads": 5, "skip_historical": True}}).json()
        assert client.put(f"/api/programs/{first['slug']}/default-profile", json={"profile_id": profile["id"]}).status_code == 200
        again = client.post(f"/api/programs/{first['slug']}/rescan").json()
        config = client.get(f"/api/scans/{again['scan_id']}/config").json()
        assert config["depth"] == "passive" and config["threads"] == 5 and config["skip_historical"] is True
        assert set(config["categories_enabled"]) == {"web", "cidr"}  # scope choices are the draft's own, not the profile's
        assert client.put(f"/api/programs/{first['slug']}/default-profile", json={"profile_id": 9999}).json()["error"]["code"] == "profile_not_found"
        assert client.put("/api/programs/nope/default-profile", json={"profile_id": None}).json()["error"]["code"] == "program_not_found"
        client.delete(f"/api/profiles/{profile['id']}")  # deleting the profile clears the default; later drafts fall back
        later = client.post(f"/api/programs/{first['slug']}/rescan").json()
        assert client.get(f"/api/scans/{later['scan_id']}/config").json()["depth"] == "light"


def test_f7_partial_profile_update_keeps_the_saved_depth(settings):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    with TestClient(create_app(settings)) as client:
        made = client.post("/api/profiles", json={"name": "calm", "based_on": "passive", "config": {}}).json()
        assert made["config"]["depth"] == "passive"
        updated = client.put(f"/api/profiles/{made['id']}", json={"name": "calm", "based_on": "passive", "config": {"threads": 1, "rate_limit": 1}}).json()
        assert updated["config"]["depth"] == "passive" and updated["config"]["threads"] == 1
        changed = client.put(f"/api/profiles/{made['id']}", json={"name": "calm", "based_on": "light", "config": {"depth": "light"}}).json()
        assert changed["config"]["depth"] == "light" and changed["config"]["threads"] == 1  # explicit depth wins, other fields kept
        assert client.put("/api/profiles/999", json={"name": "x", "config": {}}).status_code == 422
