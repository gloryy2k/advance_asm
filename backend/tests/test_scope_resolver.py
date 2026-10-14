import json
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from backend.db import Database
from backend.jobs.scope_resolver import ScopeError, ScopeResolver, classify, h1_handle
from backend.main import create_app
from backend.models import ResolveRequest


@pytest.fixture
def resolver(settings):
    db = Database(settings.BBASM_DATA / "bbasm.db")
    db.migrate()
    provider = Mock()
    provider.resolve.return_value = ([classify(v) for v in ("*.acme.com", "api.acme.com", "www.acme.com")], {"policy": "test"}, [])
    return ScopeResolver(settings, db, provider)


@pytest.mark.parametrize("value", ["h1:acme", "https://hackerone.com/acme", "https://hackerone.com/acme/policy_scopes"])
def test_tc_sr_1_2_6_h1(resolver, value):
    result = resolver.resolve(ResolveRequest(input=value))
    resolver.provider.resolve.assert_called_once()
    assert resolver.provider.resolve.call_args.args[0] == "acme"
    with resolver.database.connect() as conn:
        assert conn.execute("SELECT source FROM program").fetchone()[0] == "h1"
        assert conn.execute("SELECT count(*) FROM scope_rule WHERE kind='in'").fetchone()[0] == 3
        assert conn.execute("SELECT pattern FROM scope_rule WHERE asset_type='wildcard'").fetchone()[0] == "*.acme.com"
    assert "*.acme.com" in (resolver.settings.BBASM_TARGETS / result.slug / ".scope").read_text()


def test_tc_sr_3_and_lc_1_raw_draft_no_process(resolver, monkeypatch):
    spawn = Mock(side_effect=AssertionError("resolve must not spawn recon"))
    monkeypatch.setattr("subprocess.Popen", spawn)
    result = resolver.resolve(ResolveRequest(input="raw", scope=["*.x.com", "1.2.3.0/24", "10.0.0.5"]))
    assert set(result.assets_by_category) == {"wildcard", "cidr", "ip"}
    with resolver.database.connect() as conn:
        scan = conn.execute("SELECT * FROM scan_run").fetchone()
        assert scan["status"] == "draft"
        assert scan["trigger"] == "manual"
        assert scan["started_at"] is None
        config = conn.execute("SELECT * FROM scan_config").fetchone()
        assert config["threads"] == 50
        assert config["scan_run_id"] == result.scan_id
    spawn.assert_not_called()
    resolver.provider.resolve.assert_not_called()


@pytest.mark.parametrize("scope", [[], ["", "# comment"], ["# OUT", "acme.com"]])
def test_tc_sr_4_empty_is_422(settings, scope):
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/scope/resolve", json={"input": "raw", "scope": scope})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "scope_empty"


def test_tc_sr_5_repeat_reuses_program_and_preserves_draft_snapshot(resolver):
    first = resolver.resolve(ResolveRequest(input="h1:acme"))
    resolver.provider.resolve.return_value = ([classify("*.changed.com")], {}, [])
    second = resolver.resolve(ResolveRequest(input="h1:acme"))
    assert first.scan_id != second.scan_id
    with resolver.database.connect() as conn:
        assert conn.execute("SELECT count(*) FROM program").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM scan_config").fetchone()[0] == 2
        snapshot = json.loads(conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (first.scan_id,)).fetchone()[0])
        assert snapshot["resolved_scope"][0]["pattern"] == "*.acme.com"


def test_raw_idempotence_dedup_and_denylist(resolver):
    request = ResolveRequest(input="raw", scope=["*.x.com", "*.x.com", "# OUT", "blocked.x.com"])
    one = resolver.resolve(request)
    two = resolver.resolve(request)
    assert one.slug == two.slug
    assert one.scan_id != two.scan_id
    assert (resolver.settings.BBASM_TARGETS / one.slug / ".scope").read_text() == "# IN\n*.x.com\n# OUT\nblocked.x.com\n"
    with resolver.database.connect() as conn:
        assert conn.execute("SELECT count(*) FROM scope_rule").fetchone()[0] == 2


def test_slug_collision_is_deterministic(resolver):
    a = resolver.resolve(ResolveRequest(input="raw", scope=["acme.com"]))
    b = resolver.resolve(ResolveRequest(input="raw", scope=["*.acme.com"]))
    again = resolver.resolve(ResolveRequest(input="raw", scope=["*.acme.com"]))
    assert a.slug != b.slug == again.slug


def test_tc_cat_1_raw_and_h1_categories(resolver):
    assert classify("https://github.com/acme/repo", asset_type="SOURCE_CODE").category == "source_code"
    assert classify("com.acme.android", asset_type="GOOGLE_PLAY_APP_ID").category == "mobile"
    result = resolver.resolve(ResolveRequest(input="raw", scope=["repo:https://github.com/acme/repo", "app:com.acme", "hardware-device"]))
    assert set(result.assets_by_category) == {"source_code", "mobile", "other"}
    assert result.config.categories_enabled == ["source_code"]


@pytest.mark.parametrize("value", ["h1:--help", "h1:../acme", "https://hackerone.com.evil/acme", "https://evil@hackerone.com/acme", "https://hackerone.com/acme/other"])
def test_bad_h1_input_rejected(value):
    with pytest.raises(ScopeError):
        h1_handle(value)


def test_api_resolve_contract(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["example.com"]})
        assert response.status_code == 200
        assert response.json()["config"]["depth"] == "light"
        assert response.json()["assets_by_category"]["web"][0]["pattern"] == "example.com"
        assert client.post("/api/scope/resolve", json={"input": "h1:acme", "scope": ["evil.com"]}).status_code == 422
