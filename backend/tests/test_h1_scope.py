import json
import os
from pathlib import Path
import subprocess
from unittest.mock import Mock

import httpx
import pytest

from backend.config import PROJECT_ROOT
from backend.jobs.h1_scope import HackerOneScopeProvider
from backend.jobs.scope_resolver import ScopeError


@pytest.fixture
def metadata():
    return {"handle": "acme", "targets": {"in_scope": [
        {"asset_identifier": "*.acme.com", "asset_type": "WILDCARD"},
        {"asset_identifier": "api.acme.com", "asset_type": "URL"},
        {"asset_identifier": "https://github.com/acme/repo", "asset_type": "SOURCE_CODE", "instruction": "Read source only"},
        {"asset_identifier": "com.acme.mobile", "asset_type": "GOOGLE_PLAY_APP_ID"},
    ], "out_of_scope": [{"asset_identifier": "private.acme.com", "asset_type": "URL"}]}}


@pytest.fixture
def provider_settings(settings):
    settings.BBASM_BBROOT = PROJECT_ROOT / "vendor/claude-bug-bounty"
    return settings


def test_structured_scope_preserves_oos_wildcards_and_categories(provider_settings, metadata, tmp_path):
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json=[{**metadata, "handle": "acme-extra"}, metadata])

    def run(command, **kwargs):
        assert "--include-oos" in command
        assert command[5] == str(provider_settings.tool_path("scope_aggregator.sh").resolve())
        assert command[6] == "acme"
        assert 'source "$0" "$@"' in command[4]
        assert 'curl() { return 1; }' in command[4]
        assert 'bbscope() { return 1; }' in command[4]
        assert "H1_TOKEN" not in kwargs["env"]
        assert "BASH_ENV" not in kwargs["env"]
        assert kwargs["timeout"] == 30
        cached = json.loads((Path(kwargs["env"]["BBHUNT_CACHE_DIR"]) / "hackerone.json").read_text())
        assert cached == [metadata]
        Path(command[-1]).write_text("acme.com\nprivate.acme.com\n")
        return subprocess.CompletedProcess(command, 0)

    provider = HackerOneScopeProvider(provider_settings, httpx.MockTransport(transport), run)
    entries, policy, warnings = provider.resolve("acme", tmp_path / "audit.jsonl")
    assert len(requests) == 1
    assert entries[0].pattern == "*.acme.com"
    assert entries[-1].kind == "out"
    assert entries[2].category == "source_code"
    assert entries[3].category == "mobile"
    assert policy["assets"][2]["instruction"] == "Read source only"
    records = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert records[0]["host"] == "raw.githubusercontent.com"
    assert records[0]["decision"] == "allow"
    assert records[1]["transport"] == "disabled"


def test_api_pagination_never_follows_untrusted_next(provider_settings, tmp_path):
    provider_settings = type(provider_settings)(**{**provider_settings.model_dump(), "H1_USER": "test-user", "H1_TOKEN": "test-token"}, _env_file=None)
    requests = []

    def transport(request):
        requests.append(request)
        assert request.url.host == "api.hackerone.com"
        assert request.headers["authorization"].startswith("Basic ")
        if not request.url.path.endswith("structured_scopes"):
            return httpx.Response(200, json={"data": {"attributes": {"handle": "acme", "policy": "Program policy"}}})
        page = request.url.params["page[number]"]
        return httpx.Response(200, json={"data": [{"attributes": {
            "asset_identifier": "*.acme.com" if page == "1" else "private.acme.com",
            "asset_type": "WILDCARD" if page == "1" else "URL",
            "eligible_for_submission": page == "1", "instruction": "Policy text",
        }}], "links": {"next": "https://evil.invalid/steal" if page == "1" else None}})

    provider = HackerOneScopeProvider(provider_settings, httpx.MockTransport(transport), Mock(return_value=subprocess.CompletedProcess([], 0)))
    entries, policy, warnings = provider.resolve("acme", tmp_path / "audit.jsonl")
    assert len(requests) == 3
    assert [e.kind for e in entries] == ["in", "out"]
    assert policy["program"]["policy"] == "Program policy"
    assert warnings == []


def test_missing_token_and_failed_api_fall_back_without_leaking_auth(provider_settings, metadata, tmp_path):
    provider_settings = type(provider_settings)(**{**provider_settings.model_dump(), "H1_USER": "u", "H1_TOKEN": "secret"}, _env_file=None)
    requests = []

    def transport(request):
        requests.append(request)
        if request.url.host == "api.hackerone.com":
            return httpx.Response(401)
        assert "authorization" not in request.headers
        return httpx.Response(200, json=[metadata])

    provider = HackerOneScopeProvider(provider_settings, httpx.MockTransport(transport), Mock(return_value=subprocess.CompletedProcess([], 0)))
    entries, _, warnings = provider.resolve("acme", tmp_path / "audit.jsonl")
    assert len(requests) == 2
    assert entries
    assert warnings == ["HackerOne API unavailable; using public metadata"]
    assert "secret" not in (tmp_path / "audit.jsonl").read_text()


def test_redirects_fail_closed(provider_settings, tmp_path):
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://evil.invalid"})

    run = Mock()
    provider = HackerOneScopeProvider(provider_settings, httpx.MockTransport(transport), run)
    with pytest.raises(ScopeError):
        provider.resolve("acme", tmp_path / "audit.jsonl")
    assert len(calls) == 1
    run.assert_not_called()


@pytest.mark.parametrize("payload", [
    [{"handle": "acme-extra", "targets": {"in_scope": ["evil.com"], "out_of_scope": []}}],
    [{"handle": "acme", "targets": ["acme.com", "private.acme.com"]}],
    [{"handle": "acme", "targets": {"in_scope": ["acme.com"]}}],
])
def test_ambiguous_or_unlabelled_metadata_rejected(provider_settings, tmp_path, payload):
    run = Mock()
    provider = HackerOneScopeProvider(provider_settings, httpx.MockTransport(lambda r: httpx.Response(200, json=payload)), run)
    with pytest.raises(ScopeError):
        provider.resolve("acme", tmp_path / "audit.jsonl")
    run.assert_not_called()


def test_aggregator_timeout_does_not_return_scope(provider_settings, metadata, tmp_path):
    run = Mock(side_effect=subprocess.TimeoutExpired("bash", 30))
    provider = HackerOneScopeProvider(provider_settings, httpx.MockTransport(lambda r: httpx.Response(200, json=[metadata])), run)
    with pytest.raises(ScopeError, match="timed out"):
        provider.resolve("acme", tmp_path / "audit.jsonl")


@pytest.mark.integration
@pytest.mark.skipif(os.name != "posix", reason="Pinned Bash adapter runs in Linux/WSL2")
def test_real_offline_aggregator_adapter(provider_settings, metadata, tmp_path):
    provider = HackerOneScopeProvider(provider_settings, httpx.MockTransport(lambda r: httpx.Response(200, json=[metadata])))
    entries, _, warnings = provider.resolve("acme", tmp_path / "audit.jsonl")
    assert entries[0].pattern == "*.acme.com"
    assert entries[-1].kind == "out"
    assert not warnings
