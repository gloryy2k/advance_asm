"""Policy header: configuration, per-program default, hints from the policy text, and what is never accepted."""
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.main import create_app
from backend.models import ScanConfig
from backend.trust import required_headers

BASE = dict(depth="light", threads=5, rate_limit=5, scan_timeout=300, nuclei_severity="", skip_nmap=True, skip_nuclei=True,
            skip_active_crawl=False, categories_enabled=["web"])


def test_header_validation_is_strict_and_normalised():
    ok = ScanConfig(**BASE, request_headers=["X-HackerOne-Research:   me "])
    assert ok.request_headers == ["X-HackerOne-Research: me"]
    for bad in ("Cookie: a=b", "Authorization: Bearer x", "Host: evil", "X-A: line1\nX-B: y", "X-A:", "no-colon", "X-A: \x00",
                "Proxy-Authorization: x", "Sec-Fetch-Mode: cors", "X-" + "A" * 80 + ": v", "X-A: " + "v" * 201):
        with pytest.raises(ValidationError):
            ScanConfig(**BASE, request_headers=[bad])
    with pytest.raises(ValidationError):
        ScanConfig(**BASE, request_headers=[f"X-A{i}: v" for i in range(6)])          # at most five


def test_header_and_path_option_are_not_part_of_a_profile():
    from backend.models import RECIPE_FIELDS
    assert "request_headers" not in RECIPE_FIELDS and "allow_active_on_path_rules" not in RECIPE_FIELDS


def test_policy_text_hints_which_header_is_required_without_inventing_a_value():
    policy = {"policy_text": "Please add the header `X-HackerOne-Research: [H1 username]` to all requests. Also X-Forwarded-For: 1.2.3.4",
              "user_policy_text": "X-Bugcrowd-Research: yes"}
    assert required_headers(policy) == ["X-HackerOne-Research", "X-Bugcrowd-Research"]      # unrelated headers are not suggested
    assert required_headers({}) == [] and required_headers({"policy_text": "no headers here"}) == []


def test_program_default_is_saved_validated_and_seeds_the_next_draft(settings):
    with TestClient(create_app(settings)) as client:
        first = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["a.example.com"], "name": "acme"}).json()
        assert client.get(f"/api/scans/{first['scan_id']}/config").json()["request_headers"] == []
        denied = client.put("/api/programs/acme/request-headers", json={"headers": ["Cookie: s=1"]})
        assert denied.status_code == 422 and denied.json()["error"]["code"] == "invalid_header"
        saved = client.put("/api/programs/acme/request-headers", json={"headers": ["X-HackerOne-Research: me"]}).json()
        assert saved["request_headers"] == ["X-HackerOne-Research: me"]
        assert client.get("/api/programs/acme/summary").json()["request_headers"] == ["X-HackerOne-Research: me"]
        second = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["a.example.com"], "name": "acme"}).json()
        assert client.get(f"/api/scans/{second['scan_id']}/config").json()["request_headers"] == ["X-HackerOne-Research: me"]
        client.put("/api/programs/acme/request-headers", json={"headers": []})
        assert client.get("/api/programs/acme/summary").json()["request_headers"] == []
        assert client.put("/api/programs/nope/request-headers", json={"headers": []}).status_code == 422


def test_review_shows_header_hints_from_the_drafts_policy(settings):
    from backend.models import ResolveRequest
    from backend.tests.p2_helpers import environment
    db, resolver, _ = environment(settings, ["a.example.com"])
    result = resolver.resolve(ResolveRequest(input="raw", scope=["a.example.com"], policy_text="Send X-HackerOne-Research: [username]"))
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/scans/{result.scan_id}/review").json()["request_header_hints"] == ["X-HackerOne-Research"]


def test_schema_is_at_version_4_and_old_databases_gain_the_columns(tmp_path):
    import sqlite3
    from backend.db import Database
    from backend.migrations import SCHEMA_VERSION
    from backend.tests.test_db import build_v1
    path = tmp_path / "bbasm.db"
    build_v1(path)
    Database(path).migrate()
    conn = sqlite3.connect(path)
    assert SCHEMA_VERSION == 4 and conn.execute("SELECT version FROM schema_meta").fetchone()[0] == 4
    assert "request_headers_json" in [r[1] for r in conn.execute("PRAGMA table_info(program)")]
    assert "scope_selection_json" in [r[1] for r in conn.execute("PRAGMA table_info(program)")]
    assert {"last_error", "last_error_at"} <= {r[1] for r in conn.execute("PRAGMA table_info(schedule)")}
