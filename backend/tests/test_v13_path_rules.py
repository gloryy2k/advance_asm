"""Wolt #31: OUT rules written as URLs with a path were turned into "deny the whole host" (4,107 wolt.com URLs lost)."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from backend.jobs.ingest import Ingester
from backend.jobs.recon_orch import ReconOrchestrator
from backend.jobs.safe_path_probe import run as run_path_probe, simple_candidate
from backend.scope_gate import ScopeGate, url_rule
from backend.tests.p2_helpers import environment, write_output

# The real Wolt scope (public program page), as exported to .scope by the QA stack.
IN = ["*.wolt.com", "wolt.com", "merchant.wolt.com", "restaurant-api.wolt.com", "drive.wolt.com"]
OUT = ["*.pipedrive.com", "gettest.wolt.com", "wolt.typeform.com", "press.wolt.com",
       "https://wolt.com/en/wolt-for-work-contact-request",
       "https://merchant.wolt.com/app/partner-with-wolt",
       "https://restaurant-api.wolt.com/v1/waw-api/corporate-leads",
       "https://merchant.wolt.com/api/merchant-onboarding/merchant-admin/inbound-merchant"]


@pytest.fixture
def gate(settings, tmp_path):
    settings.BBASM_BBROOT = __import__("backend.config", fromlist=["PROJECT_ROOT"]).PROJECT_ROOT / "vendor/claude-bug-bounty"
    return ScopeGate(IN, OUT, tmp_path / "audit.jsonl", settings)


def test_a_url_out_rule_blocks_that_path_and_below_but_not_the_host(gate):
    assert gate.in_scope("wolt.com") and gate.in_scope("https://wolt.com/") and gate.in_scope("https://wolt.com/en/fin/helsinki")
    for blocked in ("https://wolt.com/en/wolt-for-work-contact-request", "https://wolt.com/en/wolt-for-work-contact-request/",
                    "https://wolt.com/en/wolt-for-work-contact-request/step2?x=1", "http://WOLT.com/EN/wolt-for-work-contact-request",
                    "https://wolt.com/en/./wolt-for-work-contact-request", "https://wolt.com/en/x/../wolt-for-work-contact-request",
                    "https://wolt.com/en/%77olt-for-work-contact-request",
                    "https://merchant.wolt.com/app/partner-with-wolt", "https://restaurant-api.wolt.com/v1/waw-api/corporate-leads"):
        assert not gate.in_scope(blocked), blocked
    for allowed in ("https://wolt.com/en/wolt-for-work", "https://wolt.com/en/wolt-for-work-contact-requests",
                    "https://merchant.wolt.com/app/menu", "https://drive.wolt.com/en/wolt-for-work-contact-request",
                    "https://restaurant-api.wolt.com/v1/orders"):
        assert gate.in_scope(allowed), allowed          # sibling paths and other hosts are untouched: nothing is widened
    assert not gate.in_scope("press.wolt.com") and not gate.in_scope("gettest.wolt.com")   # host-level OUT rules still deny the host


def test_path_rule_hosts_and_audit_name_the_rule(gate, tmp_path):
    assert gate.path_rule_hosts() == {"wolt.com": ["/en/wolt-for-work-contact-request"], "merchant.wolt.com": [
        "/app/partner-with-wolt", "/api/merchant-onboarding/merchant-admin/inbound-merchant"],
        "restaurant-api.wolt.com": ["/v1/waw-api/corporate-leads"]}
    gate.in_scope("https://wolt.com/en/wolt-for-work-contact-request")
    records = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert records[-1]["decision"] == "deny" and records[-1]["rule"] == "url:wolt.com/en/wolt-for-work-contact-request"


def test_a_host_only_or_root_url_is_still_a_host_rule():
    assert url_rule("https://wolt.com/") is None and url_rule("https://wolt.com") is None and url_rule("press.wolt.com") is None
    assert url_rule("https://wolt.com/a/b?x=1#y") == ("wolt.com", "/a/b")


def test_ingest_drops_urls_under_an_out_path_and_keeps_the_rest(settings):
    db, _, result = environment(settings, ["wolt.com", "# OUT", "https://wolt.com/en/wolt-for-work-contact-request"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    command = plan.commands[0]
    write_output(command.output, "urls/all.txt", "\n".join([
        "https://wolt.com/en/wolt-for-work-contact-request", "https://wolt.com/en/wolt-for-work-contact-request/x?a=1",
        "https://wolt.com/en/fin/helsinki", "https://wolt.com/api/v1/orders", "https://other.org/x"]) + "\n")
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='running' WHERE id=?", (result.scan_id,))
    stats = Ingester(settings, db).ingest(plan)
    funnel = stats["url_funnel"]
    assert funnel["path_rule_blocked"] == 2 and funnel["by_path_rule"] == [{"rule": "wolt.com/en/wolt-for-work-contact-request", "count": 2}]
    assert funnel["in_scope"] == 2 and funnel["out_of_scope"] == 1            # the host is NOT counted as out of scope
    assert {h["host"] for h in funnel["out_of_scope_hosts"]} == {"other.org"}
    with db.connect() as conn:
        urls = {r[0] for r in conn.execute("SELECT url FROM url")}
    assert "https://wolt.com/en/fin/helsinki" in urls and not any("contact-request" in u for u in urls)


def test_hosts_with_path_rules_remain_probe_only_even_with_legacy_opt_in(settings):
    scope = ["merchant.wolt.com", "drive.wolt.com", "# OUT", "https://merchant.wolt.com/app/partner-with-wolt"]
    db, resolver, result = environment(settings, scope)
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    by_hosts = {tuple(c.hosts): c for c in plan.commands}
    restricted, free = by_hosts[("merchant.wolt.com",)], by_hosts[("drive.wolt.com",)]
    assert restricted.env["BBASM_SKIP_ACTIVE_CRAWL"] == "1" and restricted.env["BBASM_SKIP_NUCLEI"] == "1" and restricted.env["BBASM_SKIP_FFUF"] == "1"
    assert free.env["BBASM_SKIP_ACTIVE_CRAWL"] == "0"                              # the other host is unaffected
    assert any("merchant.wolt.com" in w and "chỉ được probe" in w for w in plan.warnings)

    from backend.jobs.runner import JobRunner
    new = resolver.resolve(__import__("backend.models", fromlist=["ResolveRequest"]).ResolveRequest(input="raw", scope=scope[:2], scope_out=["https://merchant.wolt.com/app/partner-with-wolt"], name="opt-in"))
    JobRunner(settings, db).config(new.scan_id, new.config.model_copy(update={"allow_active_on_path_rules": True, "skip_active_crawl": False}))
    plan2 = ReconOrchestrator(settings, db).build(new.scan_id)
    restricted2 = next(c for c in plan2.commands if c.hosts == ("merchant.wolt.com",))
    assert restricted2.env["BBASM_SKIP_ACTIVE_CRAWL"] == "1"
    assert restricted2.env["BBASM_SKIP_NUCLEI"] == "1"
    assert restricted2.env["BBASM_NO_REDIRECT"] == "1"
    assert any("ngừng dùng" in w for w in plan2.warnings)


def test_a_restricted_host_never_gets_the_deep_pass(settings):
    db, _, result = environment(settings, ["*.wolt.com", "# OUT", "https://api.wolt.com/private"])
    orch = ReconOrchestrator(settings, db)
    plan = orch.build(result.scan_id)
    write_output(plan.discoveries[0].output, "subdomains/all.txt", "api.wolt.com\nshop.wolt.com\n")
    hosts = orch.discovered_hosts(plan)
    batches = orch.probe_batches(plan, hosts)
    write_output(batches[0].output, "live/httpx_full.txt", "https://api.wolt.com [200] [1] [t] [x]\nhttps://shop.wolt.com [200] [1] [t] [x]\n")
    plan.probed_hosts.update(batches[0].hosts)
    deep = orch.deep_command(plan, batches)
    assert deep is not None and deep.hosts == ("shop.wolt.com",)                 # api.wolt.com (path rule) is probed only


def test_path_probe_candidates_are_gated_before_command(settings):
    db, _, result = environment(settings, ["127.0.0.1", "# OUT", "http://127.0.0.1/admin"])
    orch = ReconOrchestrator(settings, db)
    plan = orch.build(result.scan_id)
    restricted = next(c for c in plan.commands if c.path_restricted)
    write_output(restricted.output, "urls/gau.txt", "\n".join([
        "http://127.0.0.1/admin", "http://127.0.0.1/admin/x", "http://127.0.0.1/public",
        "http://127.0.0.1/public?token=x", "http://127.0.0.1/%61dmin", "http://evil.example/public"])+"\n")
    commands = orch.path_probe_commands(plan)
    assert len(commands) == 1
    payload = json.loads((plan.root.parent.parent.parent / ".inputs" / str(plan.scan_id) / "path-probe-0.json").read_text())
    assert payload["urls"] == ["http://127.0.0.1/public"]
    assert commands[0].env["BBASM_NO_REDIRECT"] == "1"


def test_path_probe_never_follows_redirect_or_requests_out(tmp_path, monkeypatch):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, self.headers.get("X-Research")))
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/admin")
            else:
                self.send_response(200)
            self.end_headers()

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        base = f"http://127.0.0.1:{port}"
        source = tmp_path / "input.json"
        source.write_text(json.dumps({"host": "127.0.0.1", "deny_paths": ["/admin"], "rate_limit": 20,
                                      "urls": [base + "/safe", base + "/redirect", base + "/admin",
                                               base + "/admin/x", base + "/%61dmin"]}))
        monkeypatch.setenv("BBHUNT_AUTH_HEADERS", "X-Research: fixture")
        monkeypatch.delenv("SSLKEYLOGFILE", raising=False)
        assert run_path_probe(source, tmp_path / "out") == 0
        assert seen == [("/safe", "fixture"), ("/redirect", "fixture")]
        assert (tmp_path / "out/urls/path_probe.txt").read_text().splitlines() == [base + "/safe", base + "/redirect"]
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_ambiguous_paths_are_not_active_candidates():
    for url in ("https://h.example/a/../admin", "https://h.example//admin", "https://h.example/%61dmin",
                "https://h.example/a?x=1", "https://h.example/", "https://other.example/safe"):
        assert not simple_candidate(url, "h.example"), url
    assert simple_candidate("https://h.example/safe/path", "h.example")
