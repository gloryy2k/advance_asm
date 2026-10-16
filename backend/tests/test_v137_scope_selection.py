"""F1-F3 of the input->output audit: what Review chose survives, the filtered ZIP checks every token, schedules re-check the gate."""
import asyncio
import json
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from backend.brief.export import build_export, line_tokens
from backend.jobs.recon_orch import ReconOrchestrator
from backend.main import create_app
from backend.tests.p2_helpers import write_output
from backend.tests.test_brief_export import prepared

PAST = lambda: (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()   # noqa: E731


def launched_program(client, depth="passive"):
    made = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["a.example.com", "b.example.com"], "name": "acme"}).json()
    scan = made["scan_id"]
    config = client.get(f"/api/scans/{scan}/config").json() | {
        "depth": depth, "scan_timeout": 300, "skip_nuclei": True, "skip_active_crawl": True,
        "excluded_hosts": ["b.example.com", "https://a.example.com/admin"]}      # un-ticked host + a hand-typed OUT *path*
    assert client.put(f"/api/scans/{scan}/config", json=config).status_code == 200
    assert client.post(f"/api/scans/{scan}/launch", json={}).status_code == 200
    with client.app.state.database.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='done' WHERE id=?", (scan,))
    return scan


def test_f1_review_choices_survive_rescan_and_schedule(settings):
    from backend.config import PROJECT_ROOT
    settings = settings.model_copy(update={"BBASM_RECON_DISABLED": True, "BBASM_BBROOT": PROJECT_ROOT / "vendor/claude-bug-bounty"})
    with TestClient(create_app(settings)) as client:
        launched_program(client)
        db = client.app.state.database
        again = client.post("/api/programs/acme/rescan").json()
        cfg = client.get(f"/api/scans/{again['scan_id']}/config").json()
        assert set(cfg["excluded_hosts"]) == {"b.example.com", "https://a.example.com/admin"}   # visible in the next Review

        assert client.post("/api/programs/acme/schedule", json={"interval": "daily", "depth": "passive", "enabled": True}).status_code == 200
        scheduler = client.app.state.scheduler
        scheduler.runner.adopt_queued = AsyncMock()
        with db.connect() as conn, conn:
            conn.execute("UPDATE schedule SET next_run_at=?", (PAST(),))
        scan_id = asyncio.new_event_loop().run_until_complete(scheduler.dispatch(1))
        plan = ReconOrchestrator(settings, db).build(scan_id)
        assert not plan.gate.in_scope("b.example.com")                       # the un-ticked host stays out
        assert not plan.gate.in_scope("https://a.example.com/admin/x")        # the hand-typed OUT path stays out
        assert plan.gate.in_scope("a.example.com") and plan.gate.in_scope("https://a.example.com/shop")
        assert plan.path_rules == {"a.example.com": ["/admin"]}

        # Re-ticking at the next launch is how the user brings it back: the choice is replaced, never sticky.
        draft = client.post("/api/programs/acme/rescan").json()["scan_id"]
        config = client.get(f"/api/scans/{draft}/config").json() | {"depth": "passive", "scan_timeout": 300, "skip_nuclei": True,
                                                                       "skip_active_crawl": True, "excluded_hosts": []}
        client.put(f"/api/scans/{draft}/config", json=config)
        assert client.post(f"/api/scans/{draft}/launch", json={}).status_code == 200
        assert client.get(f"/api/scans/{client.post('/api/programs/acme/rescan').json()['scan_id']}/config").json()["excluded_hosts"] == []


def test_f1_disabled_asset_groups_are_remembered_too(settings):
    from backend.scope_selection import apply_selection, selection_from_config
    from backend.jobs.scope_resolver import classify, default_config
    entries = [classify("a.example.com"), classify("10.0.0.0/24")]
    config = default_config(settings, entries)
    assert sorted(config.categories_enabled) == ["cidr", "web"]
    narrowed = config.model_copy(update={"categories_enabled": ["web"]})
    selection = selection_from_config(entries, narrowed)
    assert selection["categories_disabled"] == ["cidr"]
    assert apply_selection(default_config(settings, entries), entries, selection).categories_enabled == ["web"]


def test_f2_every_token_on_a_line_is_checked():
    cases = {
        "https://in.example/a https://out.example/b": ["https://in.example/a", "https://out.example/b"],
        "in.example [200] https://out.example/secret": ["https://out.example/secret", "http://in.example"],
        "wolt.com/en/wolt-for-work-contact-request [200]": ["http://wolt.com/en/wolt-for-work-contact-request"],
        '{"host":"in.example","matched-at":"https:\\/\\/out.example\\/x"}': ["https://out.example/x", "http://in.example"],
        "10.0.0.5 in.example": ["10.0.0.5", "http://in.example"],
        "see app.js and readme.md": [],            # file names are not hosts
    }
    for line, expected in cases.items():
        assert sorted(line_tokens(line)) == sorted(expected), line


def test_f2_escaped_urls_in_json_are_read_however_deeply_they_are_escaped():
    """Host QA (14cfbed): a JSONL value escaped twice (\\\\/) used to slip past the one-pass unescape."""
    out = "https://a.example.com/admin/x"
    lines = [r'{"host":"a.example.com","matched-at":"https:\\\\/\\\\/a.example.com\\\\/admin\\\\/x"}',
             r'{"host":"a.example.com","matched-at":"https:\\/\\/a.example.com\\/admin\\/x"}',
             r'{"matched-at":"https:\u002f\u002fa.example.com\u002fadmin\u002fx"}',
             '{"m":"{\\"u\\":\\"https:\\\\/\\\\/a.example.com\\\\/admin\\\\/x\\"}"}',
             r'see https://a.example.com/admin\\ here']
    for line in lines:
        assert out in line_tokens(line) or "https://a.example.com/admin" in line_tokens(line), line


def test_f2_filtered_zip_drops_lines_naming_any_out_host_or_path_including_hand_typed_ones(settings):
    db, result, gen = prepared(settings)
    root = gen.target(result.slug)
    gen.generate(result.slug)
    with db.connect() as conn, conn:   # what the user typed in Review's "exclude" box for this scan
        conn.execute("UPDATE scan_config SET excluded_hosts_json=?", (json.dumps(["api3.example.com", "https://app.example.com/admin"]),))
    lines = {
        "ok": "https://api.example.com/v1/x",
        "second_url_out_host": "https://api.example.com/a https://evil.com/b",
        "host_first_then_out": "api.example.com [200] https://evil.com/secret",
        "typed_host": "https://api3.example.com/x",
        "typed_path": "https://app.example.com/admin/users",
        "typed_path_no_scheme": "app.example.com/admin [200]",
        "typed_path_sibling_is_fine": "https://app.example.com/administrator",
        "nuclei_json": '{"host":"app.example.com","matched-at":"https:\\/\\/app.example.com\\/admin\\/x"}',
        "no_host_at_all": "header without host",
        "double_escaped_json": '{"host":"app.example.com","matched-at":"https:\\\\/\\\\/app.example.com\\\\/admin\\\\/x"}',
        "unicode_escaped_json": '{"matched-at":"https:\\u002f\\u002fapp.example.com\\u002fadmin\\u002fx"}',
    }
    write_output(root, "recon/scans/1/0/urls/all.txt", "\n".join(lines.values()) + "\n")
    path, _ = build_export(gen, result.slug, True, "filtered")
    with zipfile.ZipFile(path) as archive:
        kept = set(archive.read(f"{result.slug}/recon/scans/1/0/urls/all.txt").decode().splitlines())
    path.unlink()
    assert {name for name, line in lines.items() if line in kept} == {"ok", "typed_path_sibling_is_fine", "no_host_at_all"}


def test_f3_dispatch_rechecks_the_launch_gate_and_says_why_on_the_schedule(settings):
    with TestClient(create_app(settings)) as client:
        made = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["a.example.com"], "name": "gated"}).json()
        db = client.app.state.database
        with db.connect() as conn, conn:
            conn.execute("UPDATE scan_run SET status='done' WHERE id=?", (made["scan_id"],))
        assert client.post("/api/programs/gated/schedule", json={"interval": "daily", "depth": "light", "enabled": True, "automation_ack": True}).status_code == 200
        scheduler = client.app.state.scheduler
        scheduler.runner.adopt_queued = AsyncMock()

        def tick():
            with db.connect() as conn, conn:
                conn.execute("UPDATE schedule SET next_run_at=?", (PAST(),))
            return asyncio.new_event_loop().run_until_complete(scheduler.dispatch(1))

        with db.connect() as conn, conn:   # the program's data is now only a public dump: Light is no longer allowed
            conn.execute("UPDATE program SET source='h1', handle='gated', policy_json=?", (json.dumps({"policy_source": "public_dump"}),))
        try:
            tick()
            raise AssertionError("dispatch must refuse")
        except Exception as exc:
            assert getattr(exc, "code", "") == "scope_incomplete"
        with db.connect() as conn:
            assert conn.execute("SELECT count(*) FROM scan_run WHERE trigger='scheduled'").fetchone()[0] == 0
        view = client.get("/api/programs/gated/summary").json()["schedule"]
        assert view["enabled"] == 1 and "scope_incomplete" not in view["last_error"] and "Chưa đủ dữ liệu" in view["last_error"] and view["last_error_at"]
        scheduler.runner.adopt_queued.assert_not_awaited()

        with db.connect() as conn, conn:   # data is complete again: the next tick runs and clears the message
            conn.execute("UPDATE program SET source='raw'")
        assert tick() is not None
        assert client.get("/api/programs/gated/summary").json()["schedule"]["last_error"] is None


def test_f4_a_draft_keeps_the_policy_it_was_resolved_with(settings):
    with TestClient(create_app(settings)) as client:
        first = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["a.example.com"], "name": "pol",
                                                         "policy_text": "POLICY_ONE: add header X-HackerOne-Research: u"}).json()["scan_id"]
        second = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["a.example.com"], "name": "pol",
                                                          "policy_text": "POLICY_TWO: nothing special"}).json()["scan_id"]
        r1, r2 = (client.get(f"/api/scans/{n}/review").json() for n in (first, second))
        assert r1["policy"]["user_text"].startswith("POLICY_ONE") and r1["request_header_hints"] == ["X-HackerOne-Research"]
        assert r2["policy"]["user_text"].startswith("POLICY_TWO") and r2["request_header_hints"] == []
        assert r1["policy_newer"] is True and r1["newest_draft"] == second       # the older draft says a newer one exists
        assert r2["policy_newer"] is False and r2["newest_draft"] is None
        # the older draft is still judged by its own policy: Light without the header it names is refused
        client.put(f"/api/scans/{first}/config", json=client.get(f"/api/scans/{first}/config").json() | {"depth": "light"})
        blocked = client.post(f"/api/scans/{first}/launch", json={"automation_ack": True})
        assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "header_required"
        # launching a draft makes its policy the program's, together with its scope
        client.put(f"/api/scans/{first}/config", json=client.get(f"/api/scans/{first}/config").json() | {"depth": "passive", "scan_timeout": 300,
                                                                                                          "skip_nuclei": True, "skip_active_crawl": True})
        assert client.post(f"/api/scans/{first}/launch", json={}).status_code in (200, 422)
        policy = client.get("/api/programs/pol").json()["policy"]
        assert policy["user_policy_text"].startswith("POLICY_ONE")


def test_f5_out_globs_are_accepted_consistently_and_never_widen(settings):
    from backend.jobs.scope_parse import parse_box
    from backend.scope_gate import ScopeGate
    result = parse_box(["api*.example.com", "https://*.example.com/admin", "*.cdn.example.com"], box="out", default_kind="out")
    assert [r.status for r in result] == ["ok", "error", "ok"]       # host globs yes; glob host + path stays refused, with a reason
    assert "đường dẫn" in result[1].note or "Wildcard" in result[1].note
    inside = parse_box(["api*.example.com"], box="in", default_kind="in")[0]
    assert inside.status == "error"                                  # an IN glob would widen the scope: still refused
    with TestClient(create_app(settings.model_copy(update={"BBASM_RECON_DISABLED": True}))) as client:
        made = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["*.example.com"], "scope_out": ["api*.example.com"], "name": "globs"})
        assert made.status_code == 200
        scan = made.json()["scan_id"]
        cfg = client.get(f"/api/scans/{scan}/config").json() | {"excluded_hosts": ["admin*.example.com"]}
        assert client.put(f"/api/scans/{scan}/config", json=cfg).status_code == 200       # same rule as the gate (was 422)
        cfg["excluded_hosts"] = ["*bad host"]
        assert client.put(f"/api/scans/{scan}/config", json=cfg).status_code == 422


def test_strong_needs_the_users_word_before_ffuf_runs(settings):
    """Policies that forbid brute-forcing: Strong must not guess paths unless the user confirmed, or switched ffuf off."""
    from backend.api.scans import require_ffuf
    from backend.jobs.scope_resolver import ScopeError, default_config
    base = default_config(settings.model_copy(update={"BBASM_DEFAULT_DEPTH": "strong"}), [])
    import pytest
    with pytest.raises(ScopeError) as err:
        require_ffuf(base)
    assert err.value.code == "ffuf_confirm_required"
    require_ffuf(base.model_copy(update={"ffuf_confirmed": True}))
    require_ffuf(base.model_copy(update={"skip_ffuf": True}))
    require_ffuf(default_config(settings.model_copy(update={"BBASM_DEFAULT_DEPTH": "light"}), []))   # below Strong ffuf never runs


def test_intrusive_nuclei_tags_are_an_explicit_option(settings):
    from backend.jobs.recon_orch import recon_env
    from backend.jobs.scope_resolver import default_config
    config = default_config(settings, [])
    assert recon_env(settings, config, settings.BBASM_DATA)["BBASM_NUCLEI_ALLOW_INTRUSIVE"] == "0"
    assert recon_env(settings, config.model_copy(update={"nuclei_allow_intrusive": True}), settings.BBASM_DATA)["BBASM_NUCLEI_ALLOW_INTRUSIVE"] == "1"
    from backend.models import RECIPE_FIELDS
    assert "nuclei_allow_intrusive" in RECIPE_FIELDS and "ffuf_confirmed" not in RECIPE_FIELDS   # a profile may carry the first, never the second


def test_purge_drafts_only_removes_drafts_that_are_actually_old(settings):
    from backend.jobs.runner import JobRunner
    from backend.tests.p2_helpers import environment
    db, _, result = environment(settings, ["a.example.com"])
    runner = JobRunner(settings, db)
    assert runner.purge_drafts(days=7) == 0                         # a fresh draft stays
    with db.connect() as conn, conn:
        conn.execute("DELETE FROM scan_config")                      # a draft whose config row is missing used to be purged at every boot
    assert runner.purge_drafts(days=7) == 0
    with db.connect() as conn, conn:
        conn.execute("INSERT INTO scan_config(scan_run_id,created_at) VALUES(?,?)", (result.scan_id, "2020-01-01T00:00:00.000Z"))
    assert runner.purge_drafts(days=7) == 1                          # really old: gone


def test_path_rules_read_paths_the_way_a_server_does(settings, tmp_path):
    from backend.scope_gate import ScopeGate
    from backend.config import PROJECT_ROOT
    settings.BBASM_BBROOT = PROJECT_ROOT / "vendor/claude-bug-bounty"
    gate = ScopeGate(["wolt.com"], ["https://wolt.com/admin"], tmp_path / "a.jsonl", settings)
    for blocked in ("https://wolt.com/admin;x=1", "https://wolt.com/admin;jsessionid=1/users", "https://wolt.com/a/..;/admin",
                    "https://wolt.com/ADMIN/", "https://wolt.com/x/..\\admin", "https://wolt.com/%2e/admin"):
        assert not gate.in_scope(blocked), blocked
    assert gate.in_scope("https://wolt.com/administrator") and gate.in_scope("https://wolt.com/adminx;y=1")


def test_ingest_removes_urls_stored_before_an_out_path_rule_existed(settings):
    import json as _json
    from backend.jobs.ingest import Ingester
    from backend.jobs.recon_orch import ReconOrchestrator
    from backend.tests.p2_helpers import environment, write_output
    db, _, result = environment(settings, ["wolt.com", "# OUT", "https://wolt.com/admin"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='running' WHERE id=?", (result.scan_id,))
        for url in ("https://wolt.com/admin/old", "https://wolt.com/Admin;x=1", "https://wolt.com/keep/me"):
            conn.execute("INSERT INTO url(program_id,url,source,first_seen_scan,last_seen_scan) VALUES(?,?,?,?,?)", (plan.program_id, url, "gau", 0, 0))
    write_output(plan.commands[0].output, "urls/all.txt", "https://wolt.com/new\n")
    stats = Ingester(settings, db).ingest(plan)
    with db.connect() as conn:
        urls = {r[0] for r in conn.execute("SELECT url FROM url")}
    assert urls == {"https://wolt.com/keep/me", "https://wolt.com/new"} and stats["url_funnel"]["purged_stale"] == 2
