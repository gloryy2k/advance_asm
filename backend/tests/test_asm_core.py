import json

import pytest

from backend.asm.diff_engine import DiffEngine
from backend.asm.ranking import rank_program, score_asset
from backend.jobs.ingest import Ingester
from backend.jobs.recon_orch import ReconOrchestrator
from backend.models import ResolveRequest
from backend.tests.p2_helpers import environment, write_output


def observed_scan(settings, db, resolver, result, hosts, *, complete=True):
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    diff = DiffEngine(db)
    diff.capture(plan)
    output = plan.commands[0].output
    write_output(output, "subdomains/all.txt", "\n".join(hosts))
    write_output(output, "live/httpx_full.txt", "\n".join(
        f"https://{host} [200] [Home] [{tech}]" for host, tech in hosts.items()))
    stats = Ingester(settings, db).ingest(plan)
    counts = diff.apply(plan, stats["observations"], complete=complete)
    assert diff.apply(plan, stats["observations"], complete=complete) == counts
    return plan, counts


@pytest.mark.parametrize("second,expected", [
    ({"a.example.com": "nginx", "b.example.com": "nginx"}, {"new": 1, "changed": 0, "gone": 0}),
    ({}, {"new": 0, "changed": 0, "gone": 1}),
    ({"a.example.com": "GraphQL"}, {"new": 0, "changed": 1, "gone": 0}),
    ({"a.example.com": "NGINX"}, {"new": 0, "changed": 0, "gone": 0}),
])
def test_tc_df_1_to_4(settings, second, expected):
    db, resolver, first = environment(settings, ["*.example.com"])
    observed_scan(settings, db, resolver, first, {"a.example.com": "nginx"})
    result = resolver.resolve(ResolveRequest(input="raw", scope=["*.example.com"]))
    plan, counts = observed_scan(settings, db, resolver, result, second)
    assert counts == expected
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM diff_event WHERE scan_run_id=?", (plan.scan_id,)).fetchone()[0] == sum(expected.values())
        assert conn.execute("SELECT state FROM asset WHERE host='a.example.com'").fetchone()[0] == ("gone" if expected["gone"] else "active")


def test_partial_scan_never_marks_missing_gone(settings):
    db, resolver, first = environment(settings, ["*.example.com"])
    observed_scan(settings, db, resolver, first, {"a.example.com": "nginx"})
    result = resolver.resolve(ResolveRequest(input="raw", scope=["*.example.com"]))
    _, counts = observed_scan(settings, db, resolver, result, {}, complete=False)
    assert counts == {"new": 0, "changed": 0, "gone": 0}


def test_reduced_review_scope_does_not_retire_excluded_host(settings):
    from backend.jobs.runner import JobRunner
    db, resolver, first = environment(settings, ["*.example.com"])
    observed_scan(settings, db, resolver, first, {"a.example.com": "nginx"})
    result = resolver.resolve(ResolveRequest(input="raw", scope=["*.example.com"]))
    JobRunner(settings, db).config(result.scan_id, result.config.model_copy(update={"excluded_hosts": ["a.example.com"]}))
    _, counts = observed_scan(settings, db, resolver, result, {})
    assert counts["gone"] == 0


def test_returning_host_changed_and_rank_persisted(settings):
    db, resolver, first = environment(settings, ["*.example.com"])
    first_plan, _ = observed_scan(settings, db, resolver, first, {"api.example.com": "GraphQL"})
    second = resolver.resolve(ResolveRequest(input="raw", scope=["*.example.com"]))
    observed_scan(settings, db, resolver, second, {})
    rank_program(db, first_plan.program_id, second.scan_id)
    third = resolver.resolve(ResolveRequest(input="raw", scope=["*.example.com"]))
    plan, counts = observed_scan(settings, db, resolver, third, {"api.example.com": "GraphQL"})
    assert counts["changed"] == 1
    rank_program(db, plan.program_id, plan.scan_id)
    with db.connect() as conn:
        asset = dict(conn.execute("SELECT * FROM asset").fetchone())
    assert asset["rank_score"] == 4.5
    assert "fresh" not in json.loads(asset["rank_reasons_json"])


def asset(**overrides):
    return {"host": "www.example.com", "title": "", "tech_json": "[]", "status_code": 200,
            "first_seen_scan": 1, **overrides}


def test_tc_rk_1_exact_spec_formula():
    score, reasons = score_asset(asset(host="api.example.com", tech_json='["GraphQL"]'), 1)
    # TC-RK-1 matches §12.3: api + fresh + GraphQL + status_200 = 6.0.
    assert score == 6.0
    assert {"api", "graphql", "fresh"} <= set(reasons)


@pytest.mark.parametrize("depth,complete,evidence,live,changed", [
    ("light", True, True, False, 1),
    ("strong", True, True, False, 1),
    ("passive", True, True, False, 0),
    ("light", False, True, False, 0),
    ("light", True, False, False, 0),
    ("light", True, True, True, 0),
])
def test_offline_diff_requires_completed_probe(settings, depth, complete, evidence, live, changed):
    db, resolver, first = environment(settings, ["a.example.com"])
    observed_scan(settings, db, resolver, first, {"a.example.com": "nginx"})
    settings.BBASM_DEFAULT_DEPTH = depth
    result = resolver.resolve(ResolveRequest(input="raw", scope=["a.example.com"]))
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    diff = DiffEngine(db)
    diff.capture(plan)
    output = plan.commands[0].output
    write_output(output, "subdomains/all.txt", "a.example.com\n")
    if evidence:
        write_output(output, "live/httpx_full.txt", "")
        write_output(output, "live/urls.txt", "https://a.example.com\n" if live else "")
    stats = Ingester(settings, db).ingest(plan)
    assert diff.apply(plan, stats["observations"], complete=complete)["changed"] == changed
    with db.connect() as conn:
        status = conn.execute("SELECT status_code FROM asset WHERE host='a.example.com'").fetchone()[0]
        assert status == (None if changed else 200)
        if changed:
            detail = conn.execute("SELECT detail_json FROM diff_event WHERE scan_run_id=?", (plan.scan_id,)).fetchone()[0]
            assert json.loads(detail)["status_code"] == {"before": 200, "after": None}


def test_tc_rk_2_plain_www():
    assert score_asset(asset(), 1)[0] == 2.0


@pytest.mark.parametrize("severity,delta", [("medium", 2), ("high", 2), ("critical", 2), ("low", 1), ("info", 0)])
def test_tc_rk_3_nuclei_weight(severity, delta):
    assert score_asset(asset(), 1, severities=[severity, severity])[0] == 2 + delta


def test_tc_rk_4_clamp():
    score, _ = score_asset(asset(host="api.dev.example.com", title="admin login", status_code=403,
                               tech_json='["GraphQL", "Jenkins"]'), 1, severities=["critical"])
    assert score == 10
    assert score_asset(asset(status_code=None), 2)[0] == 0


def test_status_change_and_missing_baseline_guard(settings):
    db, resolver, first = environment(settings, ["*.example.com"])
    observed_scan(settings, db, resolver, first, {"a.example.com": "nginx"})
    second = resolver.resolve(ResolveRequest(input="raw", scope=["*.example.com"]))
    plan = ReconOrchestrator(settings, db).build(second.scan_id)
    diff = DiffEngine(db)
    with pytest.raises(ValueError, match="baseline"):
        diff.apply(plan, {}, complete=True)
    diff.capture(plan)
    write_output(plan.commands[0].output, "live/httpx_full.txt", "https://a.example.com [403] [Home] [nginx]\n")
    observations = Ingester(settings, db).ingest(plan)["observations"]
    assert diff.apply(plan, observations, complete=True)["changed"] == 1
