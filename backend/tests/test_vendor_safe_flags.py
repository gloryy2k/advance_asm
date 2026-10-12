"""Execute isolated shell functions with fake tools, never the recon pipeline."""
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from backend.config import Settings


def shell_function(filename, name):
    source = Settings().tool_path(filename).read_text(encoding="utf-8")
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
