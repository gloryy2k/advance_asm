"""AUDIT-2 input-to-command checks; all subprocesses use local fakes, no network."""
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.config import Settings
from backend.jobs.recon_orch import recon_env
from backend.jobs.runner import JobRunner
from backend.jobs.scope_resolver import ScopeResolver, safe_slug
from backend.main import create_app
from backend.models import ResolveRequest, ScanConfig, validate_header
from backend.db import Database


ROOT = Path(__file__).resolve().parent.parent


def config(**changes):
    data = dict(depth="light", threads=1, rate_limit=1, scan_timeout=60,
                nuclei_severity="low", skip_nmap=True, skip_nuclei=True,
                skip_active_crawl=False, categories_enabled=["web"])
    return ScanConfig(**(data | changes))


def write_executable(path, code):
    path.write_text(code, encoding="utf-8")
    path.chmod(0o755)


def normalized_vendor(base):
    """Windows checkout has CRLF; make private LF copies solely for Linux execution."""
    tools = base / "vendor" / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    for name in ("recon_engine.sh", "_auth_helper.sh", "banner.sh"):
        source = ROOT / "vendor" / "claude-bug-bounty" / "tools" / name
        target = tools / name
        target.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
        target.chmod(0o755)
    return tools


def validation_checks(base):
    bad = {}
    for name, changes in {
        "header_lf": {"request_headers": ["X-QA: okay\nInjected: nope"]},
        "header_auth": {"request_headers": ["Authorization: Bearer fake"]},
        "url_pattern_shell": {"url_exclude_patterns": ["/x;printf_QA"]},
        "custom_id_shell": {"nuclei_custom": ["qa;printf_QA"]},
    }.items():
        try:
            config(**changes)
            bad[name] = False
        except ValidationError:
            bad[name] = True
    settings = Settings(_env_file=None, BBASM_BBROOT=ROOT / "vendor/claude-bug-bounty",
                        BBASM_DATA=base / "data", BBASM_TARGETS=base / "targets",
                        BBASM_UPDATE_TEMPLATES="0", BBASM_RECON_DISABLED=True)
    runner = JobRunner(settings, Database(settings.BBASM_DATA / "bbasm.db"))
    try:
        runner._validate(config(excluded_hosts=["bad;printf_QA.localhost"]))
        bad["excluded_host_shell"] = False
    except Exception:
        bad["excluded_host_shell"] = True
    resolver = ScopeResolver(settings, runner.database, None)
    runner.database.migrate()
    try:
        scope_result = resolver.resolve(ResolveRequest(input="raw", scope=["127.0.0.1;printf_QA"]))
        scope_patterns = [entry.pattern for group in scope_result.assets_by_category.values() for entry in group]
        bad["scope_shell"] = False
    except Exception:
        scope_patterns = []
        bad["scope_shell"] = True
    print("VALIDATION", json.dumps({"rejected": bad,
                                     "scope_patterns": scope_patterns,
                                     "safe_slug": safe_slug("qa;$(printf QA)/../program")}))

    # Values containing shell syntax are allowed as plain printable header text.
    # They must remain one argv item, and no command substitution must execute.
    literal = "X-QA-Research: qa$(touch " + str(base / "injected") + ")"
    normalized = validate_header(literal)
    environment = recon_env(settings, config(request_headers=[normalized]), base / "out")
    helper = normalized_vendor(base) / "_auth_helper.sh"
    probe = subprocess.run(["bash", "-c", f'. {shlex.quote(str(helper))}; printf "%s\\n" "${{BB_AUTH_ARGS[@]}}"'],
                           cwd=ROOT, env=environment, capture_output=True, text=True, check=True, timeout=5)
    argv = probe.stdout.splitlines()
    print("HEADER_ARGV", json.dumps({"argv_items": len(argv),
                                     "flag_and_literal_value_preserved": argv == ["-H", normalized],
                                     "env_has_header": "BBHUNT_AUTH_HEADERS" in environment,
                                     "stderr": probe.stderr[-200:],
                                     "command_substitution_executed": (base / "injected").exists(),
                                     "discovery_has_header": "BBHUNT_AUTH_HEADERS" in recon_env(settings, config(request_headers=[normalized]), base / "out", discovery=True)}))


def custom_template_check(base):
    settings = Settings(_env_file=None, BBASM_BBROOT=ROOT / "vendor/claude-bug-bounty",
                        BBASM_DATA=base / "data", BBASM_TARGETS=base / "targets",
                        BBASM_NUCLEI_TEMPLATES=base / "templates", BBASM_UPDATE_TEMPLATES="0",
                        BBASM_RECON_DISABLED=True)
    # Only validation is faked; no nuclei process or target query runs.
    with TestClient(create_app(settings)) as client:
        client.app.state.templates.run = lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", "")
        yaml = """id: qa-dns-outside\ninfo:\n  name: QA DNS only\n  author: qa\n  severity: info\ndns:\n  - name: other.localhost\n    type: A\n"""
        response = client.post("/api/tools/templates/custom", json={"content": yaml})
        print("CUSTOM_DNS", json.dumps({"status": response.status_code,
                                        "accepted": response.status_code == 200,
                                        "id": response.json().get("id")}))
        if shutil.which("nuclei", path=settings.tool_search_path()):
            client.app.state.templates.run = subprocess.run
            real_response = client.post("/api/tools/templates/custom", json={"content": yaml.replace("qa-dns-outside", "qa-dns-real")})
            print("CUSTOM_DNS_REAL_VALIDATE", json.dumps({"status": real_response.status_code,
                                                           "accepted": real_response.status_code == 200,
                                                           "error_code": (real_response.json().get("error") or {}).get("code")}))


def engine_js_header_check(base):
    tools = normalized_vendor(base)
    home = base / "home"
    fakebin = home / "go" / "bin"
    fakebin.mkdir(parents=True)
    curl_log = base / "curl.jsonl"
    write_executable(fakebin / "curl", '''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["QA_CURL_LOG"], "a", encoding="utf-8") as f: f.write(json.dumps(sys.argv[1:]) + "\\n")
if any(x.endswith(".js") for x in sys.argv[1:]): print('"/api/fixture"')
''')
    write_executable(fakebin / "gau", '''#!/usr/bin/env python3
print("http://127.0.0.2/out-of-scope.js")
''')
    write_executable(fakebin / "httpx", '''#!/usr/bin/env python3
import sys
if "-version" in sys.argv: print("projectdiscovery httpx"); sys.exit(0)
if "-o" in sys.argv:
    with open(sys.argv[sys.argv.index("-o")+1], "w") as f: f.write("http://a.localhost [200] [qa]\\n")
''')
    for name in ("katana", "dig"):
        write_executable(fakebin / name, "#!/bin/sh\nexit 0\n")
    target_list = base / "a.localhost.txt"
    target_list.write_text("a.localhost\n", encoding="utf-8")
    output = base / "recon"
    env = dict(os.environ)
    env.update(HOME=str(home), PATH=str(fakebin) + os.pathsep + os.environ["PATH"],
               QA_CURL_LOG=str(curl_log), RECON_OUT_DIR=str(output),
               BBHUNT_AUTH_HEADERS="X-QA-Research: qa-marker",
               BBASM_MANAGED="1", BBASM_SKIP_HISTORICAL="0", BBASM_SKIP_HTTPX="0",
               BBASM_SKIP_NMAP="1", BBASM_SKIP_NUCLEI="1", BBASM_SKIP_FFUF="1",
               BBASM_SKIP_CICD="1", BBASM_SKIP_ACTIVE_CRAWL="0")
    result = subprocess.run(["bash", str(tools / "recon_engine.sh"), str(target_list), "--quick"],
                            cwd=base, env=env, capture_output=True, text=True, timeout=30)
    if not curl_log.exists():
        print("ENGINE_DIAG", json.dumps({"exit": result.returncode, "stdout_tail": result.stdout[-700:], "stderr_tail": result.stderr[-700:]}))
        return
    calls = [json.loads(line) for line in curl_log.read_text(encoding="utf-8").splitlines()]
    foreign = [args for args in calls if "http://127.0.0.2/out-of-scope.js" in args]
    print("JS_HEADER", json.dumps({"engine_exit": result.returncode,
                                  "foreign_js_curl_calls": len(foreign),
                                  "foreign_js_calls_with_header": sum("X-QA-Research: qa-marker" in args for args in foreign),
                                  "header_value_in_engine_stdout": "qa-marker" in result.stdout,
                                  "gau_url_in_merged_output": "http://127.0.0.2/out-of-scope.js" in (output / "urls/all.txt").read_text(encoding="utf-8")}))


with tempfile.TemporaryDirectory() as folder:
    base = Path(folder)
    validation_checks(base / "validate")
    custom_template_check(base / "template")
    engine_js_header_check(base / "engine")
