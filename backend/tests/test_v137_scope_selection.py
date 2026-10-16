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
