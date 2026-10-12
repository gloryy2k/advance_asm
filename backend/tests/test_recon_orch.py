from pathlib import Path

import pytest

from backend.jobs.recon_orch import ReconOrchestrator
from backend.jobs.runner import JobRunner
from backend.models import ResolveRequest
from backend.tests.p2_helpers import environment, write_output


@pytest.mark.parametrize("scope,skip", [
    (["127.0.0.1"], "1"), (["::1"], "1"), (["192.0.2.0/30"], "1"),
    (["a.example.com"], "0"), (["*.example.com"], "0"),
    (["a.example.com", "127.0.0.1"], "0"),
])
def test_historical_ip_cidr_and_domain_mapping(settings, scope, skip):
    db, _, result = environment(settings, scope)
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    assert plan.commands
    assert all(c.env["BBASM_SKIP_HISTORICAL"] == skip for c in plan.commands)
    assert all(c.env["BBASM_HISTORICAL_TIMEOUT"] == "60" for c in plan.commands)


def test_historical_operator_override(settings):
    settings.BBASM_SKIP_HISTORICAL = True
    settings.BBASM_HISTORICAL_TIMEOUT = 12
    db, _, result = environment(settings)
    command = ReconOrchestrator(settings, db).build(result.scan_id).commands[0]
    assert command.env["BBASM_SKIP_HISTORICAL"] == "1"
    assert command.env["BBASM_HISTORICAL_TIMEOUT"] == "12"


@pytest.mark.parametrize("enabled", [True, False])
def test_safe_environment_toggles(settings, enabled):
    keys = ("BBASM_NO_INTERACTSH", "BBASM_NO_REDIRECT", "BBASM_SCOPE_CRAWL", "BBASM_NO_VERIFY")
    for key in keys:
        assert getattr(settings, key) is True
        setattr(settings, key, enabled)
    db, _, result = environment(settings)
    command = ReconOrchestrator(settings, db).build(result.scan_id).commands[0]
    assert all(command.env[key] == str(int(enabled)) for key in keys)


@pytest.mark.parametrize("depth,quick,nmap,httpx,crawl,nuclei", [
    ("passive", True, "1", "1", "1", "1"),
    ("light", True, "1", "0", "0", "0"),
    ("strong", False, "0", "0", "0", "0"),
])
def test_tc_ro_1_2_3_depth_mapping(settings, depth, quick, nmap, httpx, crawl, nuclei):
    settings.BBASM_DEFAULT_DEPTH = depth
    db, _, result = environment(settings)
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    command = plan.commands[0]
    assert ("--quick" in command.argv) is quick
    assert [command.env[f"BBASM_SKIP_{name}"] for name in ("NMAP", "HTTPX", "ACTIVE_CRAWL", "NUCLEI")] == [nmap, httpx, crawl, nuclei]
    assert command.env["BBASM_NUC_SEV"] == {"passive": "", "light": "low,medium", "strong": "low,medium,high,critical"}[depth]
    assert command.env["BBASM_NMAP_CONNECT"] == "1"
    assert command.env["BBASM_SKIP_CICD"] == "1"
    assert command.env["BBASM_SKIP_FFUF"] == ("0" if depth == "strong" else "1")


def test_tc_ro_4_and_lc_4_review_filters_hosts_and_passes_limits(settings):
    db, _, result = environment(settings, ["a.example.com", "b.example.com"])
    config = result.config.model_copy(update={"threads": 12, "rate_limit": 23, "excluded_hosts": ["b.example.com"]})
    JobRunner(settings, db).config(result.scan_id, config)
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    command = plan.commands[0]
    assert Path(command.argv[2]).read_text().splitlines() == ["a.example.com"]
    assert command.env["BB_THREADS"] == "12"
    assert command.env["BB_RATE_LIMIT"] == "23"
    assert command.env["NUC_RATE_LIMIT"] == "23"


def test_wildcard_discovery_is_filtered_before_active_and_apex_is_not_granted(settings):
    db, _, result = environment(settings, ["*.example.com", "# OUT", "private.example.com"])
    orch = ReconOrchestrator(settings, db)
    plan = orch.build(result.scan_id)
    assert plan.discoveries[0].env["BBASM_SKIP_HTTPX"] == "1"
    write_output(plan.discoveries[0].output, "subdomains/all.txt", "api.example.com\nexample.com\nprivate.example.com\nevil.com\n")
    followup = orch.discovered_commands(plan)
    assert len(followup) == 1
    assert Path(followup[0].argv[2]).read_text().splitlines() == ["api.example.com"]


def test_tc_cat_2_and_lc_3_source_routing_and_disabled_category(settings):
    db, resolver, result = environment(settings, ["repo:https://github.com/acme/repo", "app:com.acme"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    assert len(plan.commands) == 1
    assert plan.commands[0].argv[1] == str(settings.tool_path("secrets_hunter.sh"))
    assert plan.commands[0].argv[2:4] == ["--git", "https://github.com/acme/repo"]
    assert any("Manual asset" in message for message in plan.warnings)
    new = resolver.resolve(ResolveRequest(input="raw", scope=["repo:https://github.com/acme/repo"]))
    JobRunner(settings, db).config(new.scan_id, new.config.model_copy(update={"categories_enabled": []}))
    assert ReconOrchestrator(settings, db).build(new.scan_id).commands == []


def test_tc_ro_5_missing_script_is_warning(settings):
    db, _, result = environment(settings)
    original = settings.tool_path
    # Keep the real scope checker but simulate a missing recon script.
    from unittest.mock import patch
    with patch.object(type(settings), "tool_path", lambda self, name: Path("absent.sh") if name == "recon_engine.sh" else original(name)):
        plan = ReconOrchestrator(settings, db).build(result.scan_id)
    assert not plan.commands
    assert "missing" in plan.warnings[0]


def test_cidr_oos_overlap_never_becomes_recon_input(settings):
    db, _, result = environment(settings, ["10.0.0.0/24", "# OUT", "10.0.0.5"])
    assert ReconOrchestrator(settings, db).build(result.scan_id).commands == []
