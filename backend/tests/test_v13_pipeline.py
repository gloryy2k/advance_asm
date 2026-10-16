"""Wolt #29/#31 regressions with fake tools on PATH: no internet, no real target. Real shell scripts, real shims."""
import asyncio
import json
import os
import stat
import sys

import pytest

from backend.jobs.runner import JobRunner
from backend.models import ResolveRequest
from backend.tests.p2_helpers import environment

posix_only = pytest.mark.skipif(os.name != "posix", reason="Linux/WSL2 only")
pytestmark = [posix_only]

FAKE_SUBFINDER = """#!/bin/bash
. "$(dirname "$0")/fake.env"
out=""; while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done
for h in $FAKE_HOSTS; do echo "$h"; done > "$out"
"""
FAKE_CURL = r"""#!/usr/bin/env python3
import os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
conf = dict(l.strip().split("=", 1) for l in open(here + "/fake.env") if "=" in l)
args = sys.argv[1:]
limit = None
for i, a in enumerate(args):
    if a in ("--max-time", "-m"): limit = float(args[i + 1])
url = next((a for a in args if a.startswith("http")), "")
with open(here + "/../../fakelog/curl.log", "a") as log:
    log.write(url.split("/")[2] + " max=" + str(limit) + (" has_header" if "-H" in args else "") + "\n")
if "crt.sh" in url:
    print('[{"name_value": "mail.example.com"}]'); sys.exit(0)
if "web.archive.org" in url:
    print("http://old.example.com/x", flush=True)               # a partial answer arrives first, then the source hangs
    hang = float(conf.get("FAKE_WAYBACK_HANG", "300"))
    time.sleep(min(hang, limit) if limit else hang)
    sys.exit(28 if limit and hang > limit else 0)
sys.exit(0)
"""
FAKE_HTTPX = """#!/bin/bash
. "$(dirname "$0")/fake.env"; FAKE_LOG="$(dirname "$0")/../../fakelog"
if [ "$1" = "-version" ]; then echo "projectdiscovery.io httpx v1.0"; exit 0; fi
list=""; out=""; args=("$@")
while [ $# -gt 0 ]; do case "$1" in -l) list="$2";; -o) out="$2";; esac; shift; done
n=$(ls "$FAKE_LOG"/httpx.*.argv 2>/dev/null | wc -l); printf '%s\\n' "${args[@]}" > "$FAKE_LOG/httpx.$((n+1)).argv"
cp "$list" "$FAKE_LOG/httpx.$((n+1)).hosts"
if [ "${FAKE_HANG_CALL:-0}" = "$((n+1))" ]; then   # this call answers 3 hosts, then hangs: a batch that is cut off mid-way
  head -n 3 "$list" | while read -r h; do echo "https://$h [200] [100] [Title $h] [nginx]"; done > "$out"
  sleep 300
fi
sleep "${FAKE_HTTPX_DELAY:-0}"
while read -r h; do
  if [ -n "${FAKE_PORT:-}" ]; then echo "http://$h:$FAKE_PORT [200] [100] [Title $h] [nginx]"; else echo "https://$h [200] [100] [Title $h] [nginx]"; fi
done < "$list" > "$out"
"""


@pytest.fixture
def tools(tmp_path, monkeypatch):
    bin_dir, log = tmp_path / "go" / "bin", tmp_path / "fakelog"   # $HOME/go/bin: first place the engine and the runner look
    bin_dir.mkdir(parents=True), log.mkdir()
    for name, body in (("subfinder", FAKE_SUBFINDER), ("curl", FAKE_CURL), ("httpx", FAKE_HTTPX)):
        path = bin_dir / name
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    real_katana = os.environ.get("BBASM_TEST_REAL_KATANA")     # host QA: run the pinned katana binary instead of a stub
    if real_katana:
        import shutil
        shutil.copy(real_katana, bin_dir / "katana")
        (bin_dir / "katana").chmod(0o755)
    (bin_dir / "fake.env").write_text("")
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    monkeypatch.setenv("HOME", str(tmp_path))
    class Tools:
        def __init__(self):
            self.log = log

        def conf(self, **kv):
            (bin_dir / "fake.env").write_text("".join(f"{k}={v}\n" for k, v in kv.items()))

        bin = bin_dir

        def glob(self, pattern):
            return log.glob(pattern)

        def __truediv__(self, name):
            return log / name
    return Tools()


def run(settings, tools, scope, depth, hosts, *, timeout, scan_env=None, config=None, resolver_name=None):
    """Resolve a raw scope, run one real scan with fake tools, return (db, scan_id, stats row)."""
    conf = {"FAKE_HOSTS": '"' + " ".join(hosts) + '"', **{k: v for k, v in (scan_env or {}).items() if k.startswith("FAKE_")}}
    tools.conf(**conf)
    for key, value in (scan_env or {}).items():
        if key.startswith("BBASM_"):
            setattr(settings, key, value)
    settings.BBASM_SKIP_HISTORICAL = True      # no gau/Wayback URL collection: this covers the subdomain sources
    setattr(settings, f"BBASM_SCAN_TIMEOUT_{depth.upper()}", timeout)

    async def scenario():
        db, resolver, first = environment(settings, scope)
        result = first
        cfg = result.config.model_copy(update={"depth": depth, "scan_timeout": timeout, "skip_nmap": True, "skip_nuclei": True,
                                               "skip_active_crawl": True, **(config or {})})
        runner = JobRunner(settings, db)
        try:
            await runner.submit(result.scan_id, cfg)
            await runner.queue.join()
            return db, runner, result.scan_id
        finally:
            await runner.close()

    db, runner, scan_id = asyncio.run(scenario())
    row = runner.status(scan_id)
    return db, scan_id, row, json.loads(row["stats_json"] or "{}")


@pytest.mark.integration
def test_wayback_hang_is_bounded_and_every_source_result_is_kept(settings, tools):
    """#29: Wayback held the scan for its whole budget and subfinder/crt.sh results were lost (DB said 0)."""
    hosts = [f"h{i}.example.com" for i in range(30)]
    db, scan_id, row, stats = run(settings, tools, ["*.example.com"], "passive", hosts, timeout=60,
                                  scan_env={"BBASM_SOURCE_TIMEOUT": 2})
    wayback = [s for s in stats["sources"] if s["source"] == "web.archive.org"]
    assert wayback and wayback[0]["status"] == "timeout" and wayback[0]["seconds"] <= 4        # bounded by the shim, not by the scan
    assert any(s["source"] == "crt.sh" and s["status"] == "ok" for s in stats["sources"])
    assert stats["subs"] >= 32                                                                    # 30 subfinder + crt.sh + partial Wayback
    assert row["status"] == "done_partial" and "web.archive.org" in row["error"] and "quá thời gian" in row["error"]
    assert all("http" not in json.dumps(s) for s in stats["sources"])                           # host/outcome only, never a URL
    log = (tools / "curl.log").read_text()
    assert "crt.sh max=2.0" in log and "web.archive.org max=2.0" in log                          # the shim added a limit to bare curl calls


@pytest.mark.integration
def test_hard_stop_before_the_engine_merges_still_imports_the_partial_files(settings, tools):
    """#29 exactly: the scan is stopped while Wayback hangs; all.txt never exists; subfinder + crt.sh files must be imported."""
    hosts = [f"h{i}.example.com" for i in range(30)]
    db, scan_id, row, stats = run(settings, tools, ["*.example.com"], "passive", hosts, timeout=8,
                                  scan_env={"BBASM_SOURCE_TIMEOUT": 300})
    assert row["status"] == "done_partial" and "timeout" in row["error"]
    assert stats["subs"] >= 31          # the engine's own exit trap may or may not have merged: either way the data is in
    stage = [s for s in stats["stages"] if s["key"] == "discovery"][0]
    assert stage["status"] == "timeout"
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM asset WHERE host LIKE 'h%.example.com'").fetchone()[0] == 30


@pytest.mark.integration
def test_light_probes_every_discovered_host_in_batches_and_reports_coverage(settings, tools):
    """#31: 720 hosts were discovered and none probed because the explicit-host run used the whole budget first."""
    settings.BBASM_PROBE_BATCH = 10
    hosts = [f"h{i}.example.com" for i in range(25)]
    db, scan_id, row, stats = run(settings, tools, ["*.example.com", "portal.example.com"], "light", hosts, timeout=120,
                                  scan_env={"BBASM_SOURCE_TIMEOUT": 5, "FAKE_WAYBACK_HANG": "0"},
                                  config={"categories_enabled": ["web", "wildcard"]})
    assert stats["coverage"]["discovered"] == 27                                                 # 25 + crt.sh mail + the partial Wayback answer
    assert stats["coverage"]["probed"] == 27 and stats["coverage"]["unprobed"] == 0 and stats["coverage"]["batches"] == 3
    stages = {s["key"]: s["status"] for s in stats["stages"]}
    assert stages["discovery"] == "ok" and stages["main"] == "ok" and stages["probe"] == "ok"
    argv_files = sorted(tools.glob("httpx.*.argv"))
    assert len(argv_files) >= 4                                                                  # explicit host + 3 probe batches (+ deep)
    assert stats["live"] >= 27 and row["status"] in {"done", "done_partial"}
    probed = set()
    for hosts_file in tools.glob("httpx.*.hosts"):
        probed.update(hosts_file.read_text().split())
    assert {f"h{i}.example.com" for i in range(25)} <= probed and "portal.example.com" in probed


@pytest.mark.integration
def test_a_partial_light_scan_reports_unprobed_hosts_and_never_infers_gone(settings, tools):
    settings.BBASM_PROBE_BATCH = 5
    hosts = [f"h{i}.example.com" for i in range(30)]
    env = {"BBASM_SOURCE_TIMEOUT": 2, "FAKE_WAYBACK_HANG": "0"}
    # Scan 1 finishes: every host is probed and becomes the diff baseline.
    db, first, row1, stats1 = run(settings, tools, ["*.example.com"], "light", hosts, timeout=120, scan_env=env,
                                  config={"categories_enabled": ["web", "wildcard"]})
    assert stats1["coverage"]["unprobed"] == 0
    # Scan 2 on the same program: slow httpx, short budget, so only some batches finish.
    async def second():
        resolver = __import__("backend.jobs.scope_resolver", fromlist=["ScopeResolver"]).ScopeResolver(settings, db, __import__("unittest.mock", fromlist=["Mock"]).Mock())
        draft = resolver.resolve(ResolveRequest(input="raw", scope=["*.example.com"]))
        tools.conf(FAKE_HOSTS='"' + " ".join(hosts) + '"', FAKE_WAYBACK_HANG="0", FAKE_HTTPX_DELAY="4")
        cfg = draft.config.model_copy(update={"depth": "light", "scan_timeout": 14, "skip_nmap": True, "skip_nuclei": True,
                                              "skip_active_crawl": True, "categories_enabled": ["web", "wildcard"]})
        settings.BBASM_SCAN_TIMEOUT_LIGHT = 14
        runner = JobRunner(settings, db)
        try:
            await runner.submit(draft.scan_id, cfg)
            await runner.queue.join()
            return draft.scan_id, runner.status(draft.scan_id)
        finally:
            await runner.close()
    scan2, row2 = asyncio.run(second())
    stats2 = json.loads(row2["stats_json"])
    coverage = stats2["coverage"]
    assert coverage["unprobed"] > 0 and coverage["probed"] < coverage["discovered"]
    assert row2["status"] == "done_partial"
    assert [s for s in stats2["stages"] if s["key"] == "probe"][0]["status"] in {"timeout", "skipped_budget"}
    assert stats2["diff"]["gone"] == 0                                                         # partial: absence is not evidence
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM asset WHERE state='gone'").fetchone()[0] == 0


def test_ingest_reads_the_per_source_files_when_the_engine_never_merged_them(settings):
    """The SIGKILL case from #29: subfinder/crt.sh files on disk, no subdomains/all.txt. Scope still applies."""
    from backend.jobs.ingest import Ingester
    from backend.jobs.recon_orch import ReconOrchestrator
    from backend.tests.p2_helpers import write_output
    db, _, result = environment(settings, ["*.example.com", "# OUT", "gettest.example.com"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    discovery = plan.discoveries[0]
    write_output(discovery.output, "subdomains/subfinder.txt", "a.example.com\nb.example.com\ngettest.example.com\nunrelated.org\n")
    write_output(discovery.output, "subdomains/crtsh.txt", "c.example.com\nA.EXAMPLE.COM\n")
    write_output(discovery.output, "subdomains/wayback_subs.txt", "")
    assert not (discovery.output / "subdomains" / "all.txt").exists()
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='running' WHERE id=?", (result.scan_id,))
    stats = Ingester(settings, db).ingest(plan)
    assert stats["subs"] == 3                                    # a, b, c: OUT host, other domain and case duplicates dropped
    assert stats["partial_inputs"] and stats["partial_inputs"][0]["found"] >= 4 and stats["partial_inputs"][0]["in_scope"] == 3
    with db.connect() as conn:
        assert {r[0] for r in conn.execute("SELECT host FROM asset")} == {"a.example.com", "b.example.com", "c.example.com"}


class Recorder:
    """A localhost HTTP server standing in for the target: remembers the headers of every request it receives."""
    def __init__(self):
        import http.server
        import threading
        seen = self.seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, {k.lower(): v for k, v in self.headers.items()}))   # header names are case-insensitive (Go canonicalises them)
                self.send_response(404)
                self.end_headers()
            do_HEAD = do_GET

            def log_message(self, *args):
                pass
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.mark.integration
def test_policy_header_reaches_the_http_tools_that_run_but_never_discovery_or_the_logs(settings, tools):
    """#31 policy: "X-HackerOne-Research: <username>" on every request. Fake httpx + the engine's real curl checks hit a
    localhost server; discovery/passive traffic (crt.sh, Wayback) must not carry it, and the value must stay out of logs."""
    recorder = Recorder()
    (tools.bin / "curl").unlink()           # use the machine's real curl: the engine's exposure check must really reach the server
    try:
        header = "X-HackerOne-Research: tester-4711"
        tools.conf(FAKE_HOSTS="", FAKE_PORT=str(recorder.port), FAKE_WAYBACK_HANG="0")
        settings.BBASM_SKIP_HISTORICAL = True

        async def scenario():
            db, resolver, result = environment(settings, ["127.0.0.1"])
            cfg = result.config.model_copy(update={"depth": "light", "scan_timeout": 60, "skip_nmap": True, "skip_nuclei": True,
                                                   "skip_active_crawl": False, "request_headers": [header]})
            settings.BBASM_SCAN_TIMEOUT_LIGHT = 60
            runner = JobRunner(settings, db)
            try:
                await runner.submit(result.scan_id, cfg)
                await runner.queue.join()
                events = json.dumps(runner.logs.replay(result.scan_id))
                return db, result.scan_id, runner.status(result.scan_id), events
            finally:
                await runner.close()
        db, scan_id, row, events = asyncio.run(scenario())
        assert recorder.seen, "the config-file exposure check should have reached the localhost server"
        assert all(headers.get("x-hackerone-research") == "tester-4711" for _, headers in recorder.seen)   # every request carries it
        httpx_args = (tools.log / "httpx.1.argv").read_text().splitlines()
        assert "-H" in httpx_args and header in httpx_args                                                     # httpx got it too
        assert "tester-4711" not in events and "tester-4711" not in "".join(
            p.read_text() for p in settings.BBASM_TARGETS.rglob("audit.jsonl"))                                # not in logs or audit
        stats = json.loads(row["stats_json"])
        assert stats["request_headers"] == ["X-HackerOne-Research"] and "tester-4711" not in row["stats_json"]  # names only
    finally:
        recorder.close()


@pytest.mark.integration
def test_passive_and_discovery_never_get_the_header(settings, tools):
    tools.conf(FAKE_HOSTS='"a.example.com"', FAKE_WAYBACK_HANG="0")
    db, scan_id, row, stats = run(settings, tools, ["*.example.com"], "passive", ["a.example.com"], timeout=60,
                                  config={"request_headers": ["X-HackerOne-Research: tester-4711"]})
    assert "has_header" not in (tools / "curl.log").read_text()          # crt.sh / Wayback traffic is anonymous
    assert stats["request_headers"] == ["X-HackerOne-Research"]


def test_curl_shim_adds_the_policy_header_to_target_calls_only(tmp_path):
    """JS downloads and other curl calls in scripts that know nothing about headers still carry the policy header;
    passive source hosts never do, and a header the script already set is not duplicated."""
    import subprocess
    from backend.jobs.recon_orch import SHIM_DIR
    recorder = Recorder()
    try:
        env = {"PATH": "/usr/bin:/bin", "BBHUNT_AUTH_HEADERS": "X-HackerOne-Research: tester-4711\nX-Other: 1", "RECON_OUT_DIR": str(tmp_path)}
        curl = [str(SHIM_DIR / "curl"), "-s", "-o", "/dev/null"]
        subprocess.run([*curl, f"http://127.0.0.1:{recorder.port}/app.js"], env=env, check=True, timeout=20)
        subprocess.run([*curl, "-H", "x-other: mine", f"http://127.0.0.1:{recorder.port}/dup"], env=env, check=True, timeout=20)
        subprocess.run([*curl, f"http://localhost:{recorder.port}/passive"], env={**env, "BBASM_SOURCE_HOSTS": "localhost"}, check=True, timeout=20)
        headers = {path: h for path, h in recorder.seen}
        assert headers["/app.js"]["x-hackerone-research"] == "tester-4711" and headers["/app.js"]["x-other"] == "1"
        assert headers["/dup"]["x-hackerone-research"] == "tester-4711" and headers["/dup"]["x-other"] == "mine"   # the script's own value wins
        assert "x-hackerone-research" not in headers["/passive"]                                                    # passive source: anonymous
    finally:
        recorder.close()


# ── katana: known-files requests carry no header, so they are removed when a policy header is set ──

FAKE_KATANA = """#!/bin/bash
here="$(dirname "$0")"; n=$(ls "$here/../../fakelog"/katana.*.argv 2>/dev/null | wc -l)
printf '%s\\n' "$@" > "$here/../../fakelog/katana.$((n+1)).argv"
"""


def test_katana_shim_drops_known_files_only_when_a_policy_header_is_set(tmp_path):
    import subprocess
    from backend.jobs.recon_orch import SHIM_DIR, read_tool_notes
    bin_dir = tmp_path / "go" / "bin"
    (tmp_path / "fakelog").mkdir()
    bin_dir.mkdir(parents=True)
    (bin_dir / "katana").write_text(FAKE_KATANA)
    (bin_dir / "katana").chmod(0o755)
    out = tmp_path / "out"
    out.mkdir()
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "RECON_OUT_DIR": str(out)}
    argv = [str(SHIM_DIR / "katana"), "-list", "t.txt", "-d", "3", "-jc", "-kf", "all", "-silent", "-c", "50"]
    subprocess.run(argv, env={**env, "BBHUNT_AUTH_HEADERS": "X-HackerOne-Research: tester"}, check=True, timeout=20)
    subprocess.run(argv, env=env, check=True, timeout=20)
    with_header, without = [(tmp_path / "fakelog" / f"katana.{i}.argv").read_text().split() for i in (1, 2)]
    assert "-kf" not in with_header and "all" not in with_header                    # robots.txt/sitemap.xml are never requested
    assert with_header == ["-list", "t.txt", "-d", "3", "-jc", "-silent", "-c", "50"]  # everything else untouched
    assert "-kf" in without                                                          # no header configured: behaviour unchanged
    assert read_tool_notes(out) == [{"tool": "katana", "note": "known-files (robots.txt, sitemap.xml) tắt: katana không gắn header của policy vào các request này"}]


@pytest.mark.integration
def test_the_engine_runs_katana_through_the_wrapper_and_the_scan_reports_it(settings, tools):
    recorder = Recorder()
    (tools.bin / "curl").unlink()
    (tools.bin / "katana").write_text(FAKE_KATANA)
    (tools.bin / "katana").chmod(0o755)
    try:
        tools.conf(FAKE_HOSTS="", FAKE_PORT=str(recorder.port), FAKE_WAYBACK_HANG="0")
        settings.BBASM_SKIP_HISTORICAL = True

        async def scenario():
            db, _, result = environment(settings, ["127.0.0.1"])
            cfg = result.config.model_copy(update={"depth": "light", "scan_timeout": 60, "skip_nmap": True, "skip_nuclei": True,
                                                   "skip_active_crawl": False, "request_headers": ["X-HackerOne-Research: tester-4711"]})
            settings.BBASM_SCAN_TIMEOUT_LIGHT = 60
            runner = JobRunner(settings, db)
            try:
                await runner.submit(result.scan_id, cfg)
                await runner.queue.join()
                return runner.status(result.scan_id), json.dumps(runner.logs.replay(result.scan_id))
            finally:
                await runner.close()
        row, events = asyncio.run(scenario())
        argv = (tools.log / "katana.1.argv").read_text().split()
        assert "-kf" not in argv and "-H" in argv and "X-HackerOne-Research: tester-4711" in (tools.log / "katana.1.argv").read_text()
        stats = json.loads(row["stats_json"])
        assert stats["tool_notes"][0]["tool"] == "katana" and "known-files" in events and "tester-4711" not in events
    finally:
        recorder.close()


@pytest.mark.integration
def test_a_batch_cut_off_mid_way_keeps_its_answers_and_does_not_stop_the_other_batches(settings, tools):
    """arc-bbp #65: one timed-out batch showed "0 probed, 126 unprobed" and stopped the deep pass. Now: each command has its own
    cap, hosts that answered count as probed, and the next batches still run."""
    settings.BBASM_PROBE_BATCH = 10
    hosts = [f"h{i}.example.com" for i in range(25)]
    db, scan_id, row, stats = run(settings, tools, ["*.example.com"], "light", hosts, timeout=60,
                                  scan_env={"BBASM_SOURCE_TIMEOUT": 2, "FAKE_WAYBACK_HANG": "0", "FAKE_HANG_CALL": "1"},
                                  config={"categories_enabled": ["web", "wildcard"]})
    cov = stats["coverage"]
    assert cov["discovered"] == 27 and cov["batches"] == 3 and cov["batches_timeout"] == 1 and cov["batches_done"] == 2
    assert cov["attempted"] == 27 and cov["unreached"] == 0                                    # every batch got its turn
    assert cov["completed"] == 17 and cov["responded"] == 20                                    # 17 from finished batches + 3 from the cut one
    assert cov["probed"] == 20 and cov["unprobed"] == 7                                         # honest: the 7 silent ones are unknown, not "all 27"
    probe = [s for s in stats["stages"] if s["key"] == "probe"][0]
    assert probe["commands_timeout"] == 1 and probe["commands_ok"] == 2
    assert len(stats["unprobed_hosts"]) == 7 and not set(stats["unprobed_hosts"]) & {"h0.example.com", "h1.example.com"}   # a list a later run can target
    assert row["status"] == "done_partial" and stats["diff"]["gone"] == 0
    deep = [s for s in stats["stages"] if s["key"] == "deep"][0]
    assert deep["commands"] == 1                                                                 # the deep pass is built from the answers of ALL batches
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM asset WHERE status_code=200").fetchone()[0] >= 20
