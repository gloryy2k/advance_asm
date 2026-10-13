"""Execute isolated shell functions with fake tools, never the recon pipeline."""
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from backend.config import Settings


def shell_function(filename, name):
    source = Settings(_env_file=None).tool_path(filename).read_text(encoding="utf-8")
    return re.search(rf"(?ms)^{name}\(\) \{{.*?^\}}", source).group()


def run_shell(script, tmp_path):
    bash = shutil.which("bash")
    if os.name == "nt" and shutil.which("git"):
        git_bash = Path(shutil.which("git")).parent.parent / "bin" / "bash.exe"
        if git_bash.exists():
            bash = str(git_bash)
    if not bash:
        pytest.skip("Bash unavailable; isolated shell unit tests require Bash")
    env = {k: v for k, v in os.environ.items() if not k.startswith("BBASM_") and k not in {"BASH_ENV", "ENV"}}
    result = subprocess.run([bash, "--noprofile", "--norc"], input="set -eu\n" + script,
                            text=True, capture_output=True, cwd=tmp_path, env=env, timeout=10)
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize("value", [None, "0", "1"])
def test_tool_arguments(tmp_path, value):
    script = shell_function("recon_engine.sh", "_bbasm_tool_args") + "\n"
    if value is not None:
        script += f"BBASM_NO_REDIRECT={value}; BBASM_SCOPE_CRAWL={value}; BBASM_NO_INTERACTSH={value}\n"
    script += '''
_bbasm_tool_args
httpx() { printf 'httpx:%s\\n' "$*"; }
katana() { printf 'katana:%s\\n' "$*"; }
nuclei() { printf 'nuclei:%s\\n' "$*"; }
httpx "${BBASM_HTTPX_ARGS[@]}"
katana "${BBASM_KATANA_ARGS[@]}"
nuclei "${BBASM_NUCLEI_ARGS[@]}"
'''
    output = run_shell(script, tmp_path)
    safe = value != "0"
    assert ("-follow-redirects" not in output) is safe
    assert ("-disable-redirects" in output) is safe
    assert ("-field-scope fqdn" in output) is safe
    assert ("-no-interactsh" in output) is safe


@pytest.mark.parametrize("value", [None, "0", "1"])
def test_secret_verification_arguments(tmp_path, value):
    script = shell_function("secrets_hunter.sh", "_run_trufflehog") + "\n"
    if value is not None:
        script += f"BBASM_NO_VERIFY={value}\n"
    script += '''
OUT_DIR=.
log() { :; }
hit() { :; }
ok() { :; }
trufflehog() { printf '%s\\n' "$*"; }
_run_trufflehog https://github.com/example/repo git
cat trufflehog.jsonl
'''
    output = run_shell(script, tmp_path)
    assert ("--no-verification" in output) is (value != "0")
    assert ("--only-verified" in output) is (value == "0")


def test_history_uses_hosts_not_filename(tmp_path):
    (tmp_path / "hosts-123.txt").write_text("# approved hosts\na.example.com\nb.example.com\n", encoding="utf-8")
    script = shell_function("recon_engine.sh", "_bbasm_history_targets") + '''
TARGET_TYPE=list
TARGET=hosts-123
LIST_FILE=hosts-123.txt
_bbasm_history_targets
TARGET_TYPE=domain
TARGET=example.com
_bbasm_history_targets
'''
    assert run_shell(script, tmp_path).splitlines() == ["a.example.com", "b.example.com", "example.com"]


@pytest.mark.parametrize("hosts", ["127.0.0.1", "::1", "192.0.2.0/24", "127.0.0.1\n::1"])
def test_historical_ip_list_never_calls_provider(tmp_path, hosts):
    (tmp_path / "hosts.txt").write_text(hosts + "\n", encoding="utf-8")
    script = shell_function("recon_engine.sh", "_bbasm_history_targets") + "\n"
    script += shell_function("recon_engine.sh", "_bbasm_collect_history") + '''
RECON_DIR=.
TARGET_TYPE=list
LIST_FILE=hosts.txt
log_warn() { echo "$*"; }
gau() { echo unexpected > called; }
curl() { echo unexpected > called; }
_bbasm_collect_history
test ! -f called
'''
    assert "no domain targets" in run_shell(script, tmp_path)


def test_historical_mixed_list_filters_ips_and_bounds_gau(tmp_path):
    (tmp_path / "hosts.txt").write_text("127.0.0.1\n::1\n192.0.2.0/24\na.example.com\n", encoding="utf-8")
    script = shell_function("recon_engine.sh", "_bbasm_history_targets") + "\n"
    script += shell_function("recon_engine.sh", "_bbasm_collect_history") + '''
mkdir -p bin urls
cat > bin/timeout <<'SH'
#!/bin/bash
printf '%s\\n' "$*" > timeout_args
cat > provider_input
echo partial-output
exit 124
SH
chmod +x bin/timeout
PATH="$PWD/bin:$PATH"
gau() { :; }
RECON_DIR=.
TARGET_TYPE=list
LIST_FILE=hosts.txt
BBASM_HISTORICAL_TIMEOUT=7
log_warn() { echo "$*"; }
log_step() { :; }
_bbasm_collect_history
cat timeout_args provider_input urls/gau.txt
'''
    output = run_shell(script, tmp_path)
    assert "-k 5 7 gau --threads 20" in output
    assert "a.example.com" in output
    assert "127.0.0.1" not in output and "::1" not in output and "192.0.2" not in output
    assert "partial-output" in output
    assert "timed out" in output


def test_historical_wayback_uses_remaining_budget(tmp_path):
    script = shell_function("recon_engine.sh", "_bbasm_history_targets") + "\n"
    script += shell_function("recon_engine.sh", "_bbasm_collect_history") + '''
mkdir urls
RECON_DIR=.
TARGET_TYPE=domain
TARGET=example.com
BBASM_HISTORICAL_TIMEOUT=9
log_warn() { :; }
# Make provider selection independent of host-installed tools.
command() { if [ "$*" = "-v gau" ]; then return 1; else builtin command "$@"; fi; }
curl() { printf '%s\\n' "$*"; }
_bbasm_collect_history
cat urls/wayback.txt
'''
    output = run_shell(script, tmp_path)
    assert re.search(r"--max-time [1-9] ", output)
    assert "url=*.example.com/*" in output
