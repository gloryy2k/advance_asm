from pathlib import Path

import pytest

from backend.jobs.recon_orch import ReconOrchestrator
from backend.jobs.runner import JobRunner
from backend.models import ResolveRequest
from backend.tests.p2_helpers import environment, write_output


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
