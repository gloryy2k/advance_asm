"""P2 (Wolt #43): the server, not only the Review page, refuses Light/Strong when the policy names a header and none is set."""
import pytest

from backend.api.scans import require_headers
from backend.jobs.scope_resolver import ScopeError, default_config
from backend.trust import required_headers


def cfg(**kw):
    from backend.config import Settings
    base = default_config(Settings().model_copy(update={"BBASM_DEFAULT_DEPTH": kw.pop("depth", "light")}), [])
    return type(base).model_validate({**base.model_dump(), **kw})


HINT = ["X-HackerOne-Research"]


def test_blocks_active_depth_without_header():
    with pytest.raises(ScopeError) as err:
        require_headers(cfg(), HINT)
    assert err.value.code == "header_required"


def test_passes_with_header_case_insensitive_or_explicit_skip_or_passive():
    require_headers(cfg(request_headers=["x-hackerone-research: someone"]), HINT)
    require_headers(cfg(skip_required_headers=True), HINT)
    require_headers(cfg(depth="passive"), HINT)
    require_headers(cfg(), [])


def test_hint_detected_from_policy_text():
    assert required_headers({"policy_text": "Please add the header X-HackerOne-Research: <username> to all requests."}) == HINT


def test_confirmation_is_per_header_name_and_cleared_once_the_header_is_sent():
    require_headers(cfg(skipped_headers=["x-hackerone-research"]), HINT)
    with pytest.raises(ScopeError):   # a header the policy adds later is not covered by the old answer
        require_headers(cfg(skipped_headers=["x-hackerone-research"]), HINT + ["X-Bugcrowd-Research"])
    sent = cfg(skipped_headers=["X-HackerOne-Research"], request_headers=["X-HackerOne-Research: someone"])
    assert sent.skipped_headers == []
    with pytest.raises(ValueError):
        cfg(skipped_headers=["bad header"])


def test_api_launch_enforces_stores_and_audits_the_header_decision(settings):
    """Draft config is the single source: PUT it, read it back, launch with it; the audit names headers, never values."""
    import json
    from fastapi.testclient import TestClient
    from backend.main import create_app
    settings = settings.model_copy(update={"BBASM_RECON_DISABLED": True})
    policy = "Add the header X-HackerOne-Research: <username> to every request."
    with TestClient(create_app(settings)) as client:
        made = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["a.example.com"], "name": "acme", "policy_text": policy}).json()
        scan = made["scan_id"]
        config = client.get(f"/api/scans/{scan}/config").json() | {"depth": "light"}
        assert client.put(f"/api/scans/{scan}/config", json=config).status_code == 200
        assert client.get(f"/api/scans/{scan}/review").json()["request_header_hints"] == ["X-HackerOne-Research"]
        blocked = client.post(f"/api/scans/{scan}/launch", json={"automation_ack": True})
        assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "header_required"
        config["skipped_headers"] = ["X-HackerOne-Research"]
        client.put(f"/api/scans/{scan}/config", json=config)
        assert client.get(f"/api/scans/{scan}/config").json()["skipped_headers"] == ["X-HackerOne-Research"]   # reload shows it
        assert client.post(f"/api/scans/{scan}/launch", json={"automation_ack": True}).status_code == 200
    lines = [json.loads(l) for l in (settings.BBASM_TARGETS / "acme" / "audit.jsonl").read_text().splitlines()]
    event = next(l for l in lines if l["rule"] == "request_headers")
    assert event["required"] == ["X-HackerOne-Research"] and event["sent"] == [] and event["skipped"] == ["X-HackerOne-Research"]
