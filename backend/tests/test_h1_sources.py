"""N2: three H1 metadata sources (api > public_page > public_dump), what each one proves, and what Light/Strong may rely on.

Everything is mocked with httpx.MockTransport: no request leaves the machine."""
import json
import subprocess
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.config import PROJECT_ROOT
from backend.jobs.h1_scope import HackerOneScopeProvider, MAX_PAGE_BYTES
from backend.jobs.scope_resolver import ScopeResolver
from backend.main import create_app
from backend.trust import launch_gate

POLICY = "## Acme policy\nAutomated scanning allowed up to 5 req/s. No DoS."
NODES = [
    {"asset_type": "WILDCARD", "asset_identifier": "*.acme.com", "eligible_for_submission": True, "instruction": "Main"},
    {"asset_type": "URL", "asset_identifier": "api.acme.com", "eligible_for_submission": True, "instruction": "5 rps"},
    {"asset_type": "URL", "asset_identifier": "legacy.acme.com", "eligible_for_submission": False, "instruction": "Out"},
]


def page_response(nodes=NODES, policy=POLICY, handle="acme", has_next=False, cursor=None, totals=None):
    team = {"handle": handle, "name": "Acme", "policy": policy, "structured_scopes": {
        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor}, "edges": [{"node": n} for n in nodes]}}
    if totals is not None:  # the page's own "assets in scope" counters
        team["assets_in"], team["assets_out"] = {"total_count": totals[0]}, {"total_count": totals[1]}
    return {"data": {"team": team}}


def dump(nodes=None):
    return [{"handle": "acme", "targets": {"in_scope": [{"asset_identifier": "*.acme.com", "asset_type": "WILDCARD", "eligible_for_submission": True}],
                                           "out_of_scope": []}}]


def api_handler(request):
    if request.url.path.endswith("structured_scopes"):
        return httpx.Response(200, json={"data": [{"attributes": {"asset_identifier": "*.acme.com", "asset_type": "WILDCARD", "eligible_for_submission": True, "instruction": ""}}], "links": {}})
    return httpx.Response(200, json={"data": {"attributes": {"handle": "acme", "policy": POLICY}}})


def make_handler(*, api=True, page="ok", dump_ok=True, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request)
        host = request.url.host
        if host == "api.hackerone.com":
            return api_handler(request) if api else httpx.Response(401)
        if host == "hackerone.com":
            if page == "ok":
                return httpx.Response(200, json=page_response())
            if page == "no_policy":
                return httpx.Response(200, json=page_response(policy=""))
            if page == "changed":
                return httpx.Response(200, json={"data": {"team": None}, "errors": [{"message": "Field 'x' doesn't exist"}]})
            if page == "redirect":
                return httpx.Response(302, headers={"Location": "https://evil.invalid/"})
            if page == "huge":
                return httpx.Response(200, content=b"x" * (MAX_PAGE_BYTES + 10))
            if page == "wrong_handle":
                return httpx.Response(200, json=page_response(handle="someone-else"))
            return httpx.Response(404)
        if host == "raw.githubusercontent.com":
            return httpx.Response(200, json=dump()) if dump_ok else httpx.Response(500)
        raise AssertionError(f"unexpected host {host}")  # nothing else may ever be contacted
    return handler


@pytest.fixture
def cfg(settings):
    settings.BBASM_BBROOT = PROJECT_ROOT / "vendor/claude-bug-bounty"
    return settings


def provider(cfg, handler, token=False):
    if token:
        cfg = type(cfg)(**{**cfg.model_dump(), "H1_USER": "user", "H1_TOKEN": "tok-SECRET-123"}, _env_file=None)
    return HackerOneScopeProvider(cfg, httpx.MockTransport(handler), Mock(return_value=subprocess.CompletedProcess([], 0)))


def resolve(cfg, handler, tmp_path, token=False):
    return provider(cfg, handler, token).resolve("acme", tmp_path / "audit.jsonl")


# ── source order ────────────────────────────────────────────────────────────────

def test_api_with_token_is_preferred_and_never_touches_the_page(cfg, tmp_path):
    calls = []
    entries, policy, warnings = resolve(cfg, make_handler(calls=calls), tmp_path, token=True)
    assert policy["policy_source"] == "api" and [a["source"] for a in policy["attempts"]] == ["api"]
    assert {c.url.host for c in calls} == {"api.hackerone.com"}
    assert "tok-SECRET-123" not in json.dumps(policy) and "tok-SECRET-123" not in (tmp_path / "audit.jsonl").read_text()
    assert launch_gate("h1", policy)["allowed_depths"] == ["passive", "light", "strong"]


def test_without_a_token_the_public_page_is_read_before_the_dump(cfg, tmp_path):
    calls = []
    entries, policy, warnings = resolve(cfg, make_handler(calls=calls), tmp_path)
    assert policy["policy_source"] == "public_page" and policy["policy_text"] == POLICY and policy["fetched_at"]
    assert [(a["source"], a["ok"]) for a in policy["attempts"]] == [("api", False), ("public_page", True)]
    assert [c.url.host for c in calls] == ["hackerone.com"]                       # the dump is not needed
    assert all("authorization" not in c.headers and "cookie" not in c.headers for c in calls)
    assert calls[0].method == "POST" and calls[0].headers["user-agent"].startswith("Mozilla/5.0")
    assert [e.pattern for e in entries if e.kind == "in"] == ["*.acme.com", "api.acme.com"]
    assert [e.pattern for e in entries if e.kind == "out"] == ["legacy.acme.com"]   # eligibility, not the pool, decides IN/OUT
    assert any("trang công khai" in w for w in warnings)
    assert launch_gate("h1", policy)["allowed_depths"] == ["passive", "light", "strong"]


def test_failed_api_then_page_then_dump_each_reason_is_recorded(cfg, tmp_path):
    entries, policy, warnings = resolve(cfg, make_handler(api=False, page="missing"), tmp_path, token=True)
    assert policy["policy_source"] == "public_dump"
    assert [(a["source"], a["ok"]) for a in policy["attempts"]] == [("api", False), ("public_page", False), ("public_dump", True)]
    assert policy["attempts"][0]["reason"] == "HTTP 401" and policy["attempts"][1]["reason"] == "HTTP 404"
    assert "tok-SECRET-123" not in json.dumps(policy)


@pytest.mark.parametrize("page", ["changed", "redirect", "huge", "wrong_handle", "missing"])
def test_a_page_that_cannot_be_trusted_falls_back_to_the_dump(cfg, tmp_path, page):
    calls = []
    entries, policy, _ = resolve(cfg, make_handler(page=page, calls=calls), tmp_path)
    assert policy["policy_source"] == "public_dump" and policy["policy_text"] == ""
    expected = ["hackerone.com", "hackerone.com", "raw.githubusercontent.com"] if page == "changed" else ["hackerone.com", "raw.githubusercontent.com"]
    assert [c.url.host for c in calls] == expected   # a redirect target is never contacted; GraphQL errors get one plain retry
    assert launch_gate("h1", policy)["allowed_depths"] == ["passive"]


def test_page_pagination_follows_the_cursor_not_links(cfg, tmp_path):
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body["variables"]["cursor"])
        if body["variables"]["cursor"] is None:
            return httpx.Response(200, json=page_response(NODES[:1], has_next=True, cursor="c1"))
        return httpx.Response(200, json=page_response(NODES[1:]))
    entries, policy, _ = resolve(cfg, handler, tmp_path)
    assert seen == [None, "c1"] and len(entries) == 3 and policy["policy_source"] == "public_page"


def test_dump_failing_too_is_an_error_not_an_empty_scope(cfg, tmp_path):
    from backend.jobs.scope_resolver import ScopeError
    with pytest.raises(ScopeError):
        resolve(cfg, make_handler(page="missing", dump_ok=False), tmp_path)


# ── what may enter the scope gate ───────────────────────────────────────────────

def test_open_scope_and_over_broad_wildcards_are_listed_but_never_enter_the_gate(cfg, tmp_path):
    nodes = NODES[:2] + [
        {"asset_type": "OTHER", "asset_identifier": "Open Scope", "eligible_for_submission": True, "instruction": "Any asset we own"},
        {"asset_type": "WILDCARD", "asset_identifier": "*", "eligible_for_submission": True},
        {"asset_type": "WILDCARD", "asset_identifier": "*.com", "eligible_for_submission": True},
        {"asset_type": "URL", "asset_identifier": "All Acme properties, see policy", "eligible_for_submission": True},
    ]
    handler = lambda r: httpx.Response(200, json=page_response(nodes))
    entries, policy, warnings = resolve(cfg, handler, tmp_path)
    assert sorted(e.pattern for e in entries) == ["*.acme.com", "api.acme.com"]
    assert policy["classification"]["unclassified_count"] == 4
    assert {u["identifier"] for u in policy["classification"]["unclassified"]} == {"Open Scope", "*", "*.com", "All Acme properties, see policy"}
    assert any("KHÔNG đưa vào scope gate" in w for w in warnings)
    assert launch_gate("h1", policy)["allowed_depths"] == ["passive", "light", "strong"]   # classified IN assets remain usable


def test_only_unclassified_in_assets_means_nothing_to_scan(cfg, tmp_path):
    nodes = [{"asset_type": "OTHER", "asset_identifier": "Open Scope", "eligible_for_submission": True}]
    _, policy, _ = resolve(cfg, lambda r: httpx.Response(200, json=page_response(nodes)), tmp_path)
    gate = launch_gate("h1", policy)
    assert gate["allowed_depths"] == ["passive"] and "IN phân loại rõ" in gate["missing"]


def test_a_host_like_out_item_we_cannot_parse_blocks_active_depths(cfg, tmp_path):
    nodes = NODES[:2] + [{"asset_type": "URL", "asset_identifier": "bad_host!.acme.com", "eligible_for_submission": False}]
    _, policy, _ = resolve(cfg, lambda r: httpx.Response(200, json=page_response(nodes)), tmp_path)
    gate = launch_gate("h1", policy)
    assert gate["allowed_depths"] == ["passive"] and "OUT chưa phân loại" in gate["missing"]


def test_missing_policy_blocks_active_depths_until_the_user_supplies_it(cfg, tmp_path):
    _, policy, _ = resolve(cfg, make_handler(page="no_policy"), tmp_path)
    assert policy["policy_source"] == "public_page"
    gate = launch_gate("h1", policy)
    assert gate["allowed_depths"] == ["passive"] and "policy" in gate["missing"]
    assert launch_gate("h1", {**policy, "user_policy_text": "Scanning allowed, 2 rps"})["allowed_depths"] == ["passive", "light", "strong"]


def test_the_dump_is_never_enough_even_with_user_policy_text(cfg, tmp_path):
    _, policy, _ = resolve(cfg, make_handler(page="missing"), tmp_path)
    gate = launch_gate("h1", {**policy, "user_policy_text": "Scanning allowed"})
    assert gate["allowed_depths"] == ["passive"] and "nguồn có cấu trúc hiện hành" in gate["missing"]


def test_manual_raw_scope_is_not_gated():
    assert launch_gate("raw", {})["allowed_depths"] == ["passive", "light", "strong"]


# ── end to end through the API ──────────────────────────────────────────────────

def app_with(cfg, handler, token=False):
    app = create_app(cfg)
    app.state.scope_resolver = ScopeResolver(cfg, app.state.database, provider(cfg, handler, token))
    return app


def resolve_h1(client, **extra):
    return client.post("/api/scope/resolve", json={"input": "https://hackerone.com/acme?type=team", **extra}).json()


def test_review_shows_source_time_missing_and_blocks_light_on_the_dump(cfg):
    with TestClient(app_with(cfg, make_handler(page="missing"))) as client:
        draft = resolve_h1(client)
        review = client.get(f"/api/scans/{draft['scan_id']}/review").json()
        assert review["policy"]["source"] == "public_dump" and review["policy"]["fetched_at"]
        assert [a["source"] for a in review["policy"]["attempts"]] == ["api", "public_page", "public_dump"]
        assert review["launch_gate"]["allowed_depths"] == ["passive"] and review["trust"]["missing"]
        config = client.get(f"/api/scans/{draft['scan_id']}/config").json()
        for depth in ("light", "strong"):
            denied = client.post(f"/api/scans/{draft['scan_id']}/launch", json={"config": {**config, "depth": depth}, "automation_ack": True})
            assert denied.status_code == 422 and denied.json()["error"]["code"] == "scope_incomplete"
        assert client.get(f"/api/scans/{draft['scan_id']}").json()["status"] == "draft"
        direct = client.post("/api/scans", json={"input": "h1:acme", "depth": "light", "automation_ack": True})
        assert direct.status_code == 422 and direct.json()["error"]["code"] == "scope_incomplete"
        assert client.get("/api/drafts").json().__len__() == 1                       # the rejected one-shot left no extra draft


def test_review_on_the_public_page_allows_light_after_ack_and_labels_the_source(cfg):
    cfg.BBASM_RECON_DISABLED = True
    with TestClient(app_with(cfg, make_handler())) as client:
        draft = resolve_h1(client)
        review = client.get(f"/api/scans/{draft['scan_id']}/review").json()
        assert review["policy"]["source"] == "public_page" and review["trust"]["level"] == "public_page"
        assert review["trust"]["verified"] is False and review["policy"]["text"] == POLICY
        assert review["launch_gate"]["allowed_depths"] == ["passive", "light", "strong"]
        config = client.get(f"/api/scans/{draft['scan_id']}/config").json()
        config["depth"] = "light"
        assert client.post(f"/api/scans/{draft['scan_id']}/launch", json={"config": config}).json()["error"]["code"] == "ack_required"
        ok = client.post(f"/api/scans/{draft['scan_id']}/launch", json={"config": config, "automation_ack": True})
        assert ok.status_code == 200


def test_passive_stays_available_on_the_dump(cfg):
    cfg.BBASM_RECON_DISABLED = True
    with TestClient(app_with(cfg, make_handler(page="missing"))) as client:
        draft = resolve_h1(client)
        config = client.get(f"/api/scans/{draft['scan_id']}/config").json()
        config.update(depth="passive", scan_timeout=300, skip_nmap=True, skip_nuclei=True, skip_active_crawl=True, nuclei_severity="")
        r = client.post(f"/api/scans/{draft['scan_id']}/launch", json={"config": config})
        assert r.status_code == 200, r.text


def test_schedule_for_a_dump_program_cannot_be_light(cfg):
    with TestClient(app_with(cfg, make_handler(page="missing"))) as client:
        draft = resolve_h1(client)
        denied = client.post(f"/api/programs/{draft['slug']}/schedule", json={"interval": "daily", "depth": "light", "automation_ack": True})
        assert denied.status_code == 422 and denied.json()["error"]["code"] == "scope_incomplete"


def test_api_token_never_reaches_responses_logs_or_audit(cfg, caplog):
    with TestClient(app_with(cfg, make_handler(), token=True)) as client:
        draft = resolve_h1(client)
        text = json.dumps(client.get(f"/api/scans/{draft['scan_id']}/review").json()) + json.dumps(draft)
    assert "tok-SECRET-123" not in text and "tok-SECRET-123" not in caplog.text
    for audit in cfg.BBASM_TARGETS.rglob("audit.jsonl"):
        assert "tok-SECRET-123" not in audit.read_text()


# ── completeness: the page's own totals prove we read everything ────────────────

def test_counts_that_match_are_recorded_and_the_totals_are_asked_for(cfg, tmp_path):
    asked = []

    def handler(request):
        asked.append(json.loads(request.content)["query"])
        return httpx.Response(200, json=page_response(totals=(2, 1)))
    _, policy, _ = resolve(cfg, handler, tmp_path)
    assert "structured_scopes_search" in asked[0] and len(asked) == 1
    assert policy["completeness"] == {"in": {"fetched": 2, "total": 2}, "out": {"fetched": 1, "total": 1}}
    assert launch_gate("h1", policy)["allowed_depths"] == ["passive", "light", "strong"]


def test_a_short_read_blocks_active_depths_and_says_how_short(cfg, tmp_path):
    _, policy, _ = resolve(cfg, lambda r: httpx.Response(200, json=page_response(totals=(5, 1))), tmp_path)
    gate = launch_gate("h1", policy)
    assert gate["allowed_depths"] == ["passive"] and "asset chưa đọc đủ" in gate["missing"] and "IN 2/5" in gate["reasons"][0]


def test_when_the_page_refuses_the_totals_fields_the_plain_query_is_used_and_nothing_is_claimed(cfg, tmp_path):
    seen = []

    def handler(request):
        query = json.loads(request.content)["query"]
        seen.append("assets_in" in query)
        if "assets_in" in query:
            return httpx.Response(200, json={"data": None, "errors": [{"message": "Field 'assets_in' doesn't exist"}]})
        return httpx.Response(200, json=page_response())
    _, policy, _ = resolve(cfg, handler, tmp_path)
    assert seen == [True, False] and policy["policy_source"] == "public_page" and policy["completeness"] is None
    assert launch_gate("h1", policy)["allowed_depths"] == ["passive", "light", "strong"]   # unknown totals do not block, they are just not claimed


# ── real public shapes seen on the live check (GitLab, Shopify, Uber) ───────────

def node(identifier, asset_type, eligible=True):
    return {"asset_type": asset_type, "asset_identifier": identifier, "eligible_for_submission": eligible, "instruction": ""}


LIVE_SHAPES = [
    node("*.acme.com", "WILDCARD"),
    node("https://gitlab.com/gitlab-org/gitlab", "SOURCE_CODE"),
    node("https://github.com/Shopify/*", "SOURCE_CODE"),
    node("*.uberinternal.com", "OTHER"),
    node("Your Own GitLab Instance", "OTHER"),
    node("*ubereats.com", "OTHER"),
    node("https://gitlab.com/gitlab-org/opstrace/opstrace-ui", "SOURCE_CODE", False),
    node("https://gitlab.com/gitlab-org/cli/", "SOURCE_CODE", False),
    node("supplier-portal.shopifycloud.com", "OTHER", False),
    node("*.ubercarshare.com", "OTHER", False),
    node("*scaledsolutions.uber.com", "WILDCARD", False),
    node("scaledsolutions*.uber.com", "WILDCARD", False),
    node("Other", "OTHER", False),
    node("Fraud Reports", "OTHER", False),
]


def test_real_world_shapes_are_classified_precisely_or_left_out(cfg, tmp_path):
    entries, policy, warnings = resolve(cfg, lambda r: httpx.Response(200, json=page_response(LIVE_SHAPES)), tmp_path)
    by = {(e.kind, e.pattern): e.category for e in entries}
    assert by[("in", "repo:https://gitlab.com/gitlab-org/gitlab")] == "source_code"
    assert by[("in", "repo:https://github.com/shopify")] == "source_code"          # "/*" means the organisation, nothing wider
    assert by[("out", "repo:https://gitlab.com/gitlab-org/opstrace/opstrace-ui")] == "source_code"   # GitLab subgroups
    assert by[("out", "repo:https://gitlab.com/gitlab-org/cli")] == "source_code"
    assert by[("in", "*.uberinternal.com")] == "wildcard"                         # clean host typed OTHER: accepted by form, and said so
    assert by[("out", "supplier-portal.shopifycloud.com")] == "web" and by[("out", "*.ubercarshare.com")] == "wildcard"
    assert by[("out", "*scaledsolutions.uber.com")] == "wildcard" and by[("out", "scaledsolutions*.uber.com")] == "wildcard"
    assert ("in", "*ubereats.com") not in by                                       # cannot be an allow rule: never widened
    left = {u["identifier"]: u for u in policy["classification"]["unclassified"]}
    assert set(left) == {"Your Own GitLab Instance", "*ubereats.com", "Other", "Fraud Reports"}
    assert not left["Other"]["blocking"] and not left["Fraud Reports"]["blocking"]  # descriptions name no host
    assert {b["identifier"] for b in policy["classification"]["by_shape"]} == {"*.uberinternal.com", "supplier-portal.shopifycloud.com", "*.ubercarshare.com"}
    assert any("theo hình thức" in w for w in warnings)
    assert launch_gate("h1", policy)["allowed_depths"] == ["passive", "light", "strong"]


def test_the_scope_gate_enforces_repo_hosts_and_glob_exclusions(cfg, tmp_path):
    from backend.scope_gate import ScopeGate
    gate = ScopeGate(["*.uber.com", "repo:https://gitlab.com/gitlab-org/gitlab", "repo:https://github.com/shopify"],
                     ["*scaledsolutions.uber.com", "scaledsolutions*.uber.com", "repo:https://gitlab.com/gitlab-org/cli"],
                     tmp_path / "a.jsonl", cfg)
    assert gate.in_scope("riders.uber.com") and not gate.in_scope("scaledsolutions.uber.com")
    assert not gate.in_scope("x-scaledsolutions.uber.com") and not gate.in_scope("scaledsolutions2.uber.com")
    assert gate.in_scope("repo:https://gitlab.com/gitlab-org/gitlab") and gate.in_scope("repo:https://github.com/Shopify/hydrogen")
    assert not gate.in_scope("repo:https://gitlab.com/gitlab-org/cli") and not gate.in_scope("repo:https://gitlab.com/gitlab-org/other")
    assert not gate.in_scope("repo:https://github.com/gitlab-org/gitlab")          # same path on another host is another repository
    for bad in ("*scaled.uber.com", "repo:https://evil.com/x/y"):
        assert not gate.in_scope(bad)                                              # a glob is a rule, never an outbound target


def test_a_glob_is_never_accepted_as_an_allow_rule():
    from backend.scope_gate import normalize_pattern
    with pytest.raises(ValueError):
        normalize_pattern("*ubereats.com")
    assert normalize_pattern("*ubereats.com", deny=True) == "*ubereats.com"
