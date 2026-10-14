"""U0: tolerant, fail-closed raw scope parsing, H1 handle normalisation, preview endpoint."""
import json

from fastapi.testclient import TestClient
import pytest

from backend.db import Database
from backend.jobs.h1_scope import HackerOneScopeProvider
from backend.jobs.scope_parse import entries_or_raise, parse_scope
from backend.jobs.scope_resolver import ScopeError, ScopeResolver, h1_handle
from backend.main import create_app
from backend.models import ResolveRequest


def parsed(lines, out=()):
    return entries_or_raise(parse_scope(list(lines), list(out)))


def pairs(lines, out=()):
    entries, _ = parsed(lines, out)
    return sorted((e.pattern, e.kind, e.category) for e in entries)


@pytest.mark.parametrize("header", ["# OUT", "# out", "#OUT", "#  Out of scope", "OUT:", "# OOS", "# Excluded:"])
def test_tc_sr_7_every_out_header_spelling_makes_following_hosts_out(header):
    # F2: a mis-spelled header used to leave the host IN, i.e. scanned.
    assert pairs(["a.example.com", header, "b.example.com"]) == [
        ("a.example.com", "in", "web"), ("b.example.com", "out", "web")]


@pytest.mark.parametrize("line", ["# OUTT x", "#out-of-scopes", "# exclude everything below this"])
def test_header_lookalike_is_error_not_silently_ignored(line):
    with pytest.raises(ScopeError, match="dòng 2") as exc:
        parsed(["a.example.com", line, "b.example.com"])
    assert exc.value.code == "scope_invalid"


def test_plain_comments_and_blank_lines_are_ignored():
    assert pairs(["# production assets", "", "  ", "a.example.com"]) == [("a.example.com", "in", "web")]


def test_dedicated_out_box_is_out_and_rejects_in_header():
    assert pairs(["*.x.com"], ["admin.x.com"]) == [("*.x.com", "in", "wildcard"), ("admin.x.com", "out", "web")]
    with pytest.raises(ScopeError):
        parsed(["*.x.com"], ["# IN", "admin.x.com"])


def test_tc_sr_8_separators_bullets_comments_crlf():
    lines = ["a.example.com, b.example.com\\r".replace("\\r", "\r"), "c.example.com d.example.com; e.example.com",
             "- f.example.com  # prod", "1) g.example.com", "*.h.example.com\r"]
    assert [p[0] for p in pairs(lines)] == sorted(
        f"{x}.example.com" if x != "h" else "*.h.example.com" for x in "abcdefgh")


def test_tc_sr_9_ip_range_becomes_cidr_blocks():
    entries, warnings = parsed(["10.0.0.1-10.0.0.20", "10.0.1.5-9"])
    assert {e.pattern for e in entries} >= {"10.0.0.1", "10.0.0.2/31", "10.0.0.4/30", "10.0.1.5", "10.0.1.6/31", "10.0.1.8/31"}
    assert all(e.category in {"ip", "cidr"} for e in entries)
    assert warnings
    with pytest.raises(ScopeError):
        parsed(["10.0.0.9-10.0.0.1"])
    with pytest.raises(ScopeError):
        parsed(["10.0.0.1-10.255.255.254"])  # 46 blocks > cap


def test_non_strict_cidr_and_mid_wildcard_are_errors_with_hint():
    with pytest.raises(ScopeError, match="10.0.0.0/24"):
        parsed(["10.0.0.5/24"])
    with pytest.raises(ScopeError, match="Wildcard"):
        parsed(["api.*.example.com"])


def test_wildcard_url_port_and_github_normalisation_warn():
    entries, warnings = parsed(["https://*.example.com", "app.example.com:8443", "https://github.com/acme",
                                "github.com/acme/repo"])
    assert sorted((e.pattern, e.category) for e in entries) == [
        ("*.example.com", "wildcard"), ("app.example.com", "web"),
        ("repo:https://github.com/acme", "source_code"), ("repo:https://github.com/acme/repo", "source_code")]
    assert len(warnings) == 4


def test_url_with_path_warns_that_whole_host_is_scanned():
    entries, warnings = parsed(["https://app.example.com/login"])
    assert entries[0].category == "web" and any("cả host" in w for w in warnings)


def test_app_id_lookalike_and_bare_word_are_warned_not_trusted():
    _, warnings = parsed(["com.acme.android", "localhost"])
    assert any("app:" in w for w in warnings) and any("thủ công" in w for w in warnings)


def test_error_message_names_box_and_line_and_does_not_hide_other_lines():
    with pytest.raises(ScopeError) as exc:
        parsed(["ok.example.com", "bad host!!", "also ok.example.com"], ["x y@z"])
    message = str(exc.value)
    assert "dòng 2" in message and "ô OUT dòng 1" in message and "2 dòng lỗi" in message


@pytest.mark.parametrize("value,handle", [
    ("h1:Acme", "acme"), ("h1: acme", "acme"), ("acme", "acme"), ("@acme", "acme"),
    ("https://hackerone.com/acme", "acme"), ("https://hackerone.com/acme/", "acme"),
    ("https://hackerone.com/live_nation?type=team", "live_nation"),
    ("https://www.hackerone.com/acme#scope", "acme"), ("hackerone.com/acme", "acme"),
    ("http://hackerone.com/acme", "acme"), ("https://hackerone.com/acme/policy", "acme"),
    ("https://hackerone.com/acme/policy_scopes", "acme"), ("  https://hackerone.com/acme  ", "acme"),
])
def test_tc_sr_10_h1_input_forms(value, handle):
    assert h1_handle(value) == handle


@pytest.mark.parametrize("value", [
    "https://hackerone.com.evil/acme", "https://evil@hackerone.com/acme", "https://evil.com/acme",
    "https://hackerone.com/acme/other", "https://hackerone.com/reports/123", "https://hackerone.com/",
    "raw", "h1:--help", "h1:../acme", "a b", "ftp://hackerone.com/acme", "acme.com"])
def test_h1_input_still_rejects_foreign_or_odd_shapes(value):
    with pytest.raises(ScopeError):
        h1_handle(value)


def test_resolve_accepts_scope_out_and_surfaces_parse_warnings(settings):
    db = Database(settings.BBASM_DATA / "bbasm.db")
    db.migrate()
    resolver = ScopeResolver(settings, db)
    result = resolver.resolve(ResolveRequest(input="raw", scope=["*.x.com", "app.x.com:8443"], scope_out=["admin.x.com"]))
    assert [e.pattern for e in result.assets_by_category["wildcard"]] == ["*.x.com"]
    assert any("port" in w for w in result.warnings)
    with db.connect() as conn:
        kinds = dict(conn.execute("SELECT pattern,kind FROM scope_rule").fetchall())
    assert kinds["admin.x.com"] == "out" and kinds["app.x.com"] == "in"


def test_resolve_error_names_the_bad_line_and_creates_nothing(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["a.example.com", "bad host!!"]})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "scope_invalid"
        assert "dòng 2" in response.json()["error"]["message"]
        assert client.get("/api/programs").json() == []


def test_preview_endpoint_is_pure_and_per_line(settings):
    with TestClient(create_app(settings)) as client:
        body = client.post("/api/scope/preview", json={
            "input": "raw", "scope": ["*.x.com", "# note", "bad host!!", "10.0.0.5/24"], "scope_out": ["a.x.com"]}).json()
        assert body["ok"] is False and body["summary"]["errors"] == 2
        statuses = [(l["box"], l["line"], l["status"]) for l in body["lines"]]
        assert ("in", 1, "ok") in statuses and ("in", 2, "skip") in statuses and ("in", 3, "error") in statuses
        assert ("out", 1, "ok") in statuses
        good = client.post("/api/scope/preview", json={"input": "raw", "scope": ["x.com"]}).json()
        assert good["ok"] is True and good["summary"] == {"in": 1, "out": 0, "errors": 0, "warnings": 0}
        h1 = client.post("/api/scope/preview", json={"input": "https://hackerone.com/live_nation?type=team"}).json()
        assert h1["ok"] and h1["handle"] == "live_nation"
        bad = client.post("/api/scope/preview", json={"input": "https://evil.com/x"}).json()
        assert bad["ok"] is False and bad["message"]
        assert not settings.BBASM_DATA.exists() and not settings.BBASM_TARGETS.exists()  # nothing written


def test_tc_prg_4_h1_policy_reaches_program_md(settings, tmp_path):
    """F1 regression: use the REAL provider payload shape, not a hand-made flat dict."""
    import httpx
    from backend.brief.generator import BriefGenerator
    from backend.config import PROJECT_ROOT
    settings.BBASM_BBROOT = PROJECT_ROOT / "vendor/claude-bug-bounty"
    settings = type(settings)(**{**settings.model_dump(), "H1_USER": "u", "H1_TOKEN": "t"}, _env_file=None)

    def transport(request):
        if request.url.path.endswith("structured_scopes"):
            return httpx.Response(200, json={"data": [{"attributes": {
                "asset_identifier": "*.acme.com", "asset_type": "WILDCARD", "eligible_for_submission": True,
                "instruction": "Main"}}], "links": {}})
        return httpx.Response(200, json={"data": {"attributes": {"handle": "acme", "policy": "No DoS. 5 req/s. <!-- user-editable -->"}}})

    from unittest.mock import Mock
    import subprocess
    provider = HackerOneScopeProvider(settings, httpx.MockTransport(transport), Mock(return_value=subprocess.CompletedProcess([], 0)))
    db = Database(settings.BBASM_DATA / "bbasm.db")
    db.migrate()
    resolver = ScopeResolver(settings, db, provider)
    result = resolver.resolve(ResolveRequest(input="h1:acme", policy_text="Chỉ test giờ hành chính"))
    with db.connect() as conn:
        program = dict(conn.execute("SELECT * FROM program WHERE slug=?", (result.slug,)).fetchone())
    scope = [e.model_dump() for g in result.assets_by_category.values() for e in g]
    text = BriefGenerator.program_text("acme", program, scope)
    assert "No DoS. 5 req/s." in text and "API HackerOne" in text and "Chỉ test giờ hành chính" in text
    assert "Không có policy" not in text
    assert text.count("<!-- user-editable -->") == 1  # injected marker in policy text was stripped


def test_program_md_without_policy_says_so_and_points_to_next_step():
    from backend.brief.generator import BriefGenerator
    text = BriefGenerator.program_text("x", {"policy_json": json.dumps({"scope_identity": "x"})}, [])
    assert "Không có policy trong dữ liệu" in text
