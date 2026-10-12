"""Opt-in checks for the Linux process and shell interfaces; never run in unit CI."""

import asyncio
import os
from pathlib import Path
import subprocess
import sys

import pytest

from backend.config import PROJECT_ROOT
from backend.jobs.runner import stop_process_group

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.name != "posix", reason="Linux/WSL2 only")]


def test_tc_ro_6_passive_toggles_skip_active_commands(tmp_path):
    script = PROJECT_ROOT / "vendor/claude-bug-bounty/tools/recon_engine.sh"
    targets = tmp_path / "targets.txt"
    targets.write_text("example.com\n")
    output = tmp_path / "output"
    marker = tmp_path / "unexpected-tool"
    # No real recon tools or target network: inherited Bash functions act as sentinels.
    wrapper = '''
    nmap() { touch "$BBASM_SENTINEL"; }; export -f nmap
    dig() { touch "$BBASM_SENTINEL"; }; export -f dig
    katana() { touch "$BBASM_SENTINEL"; }; export -f katana
    nuclei() { touch "$BBASM_SENTINEL"; }; export -f nuclei
    ffuf() { touch "$BBASM_SENTINEL"; }; export -f ffuf
    curl() { touch "$BBASM_SENTINEL"; }; export -f curl
    gau() { return 0; }; export -f gau
    exec bash "$@"
    '''
    env = {**os.environ, "BBASM_SENTINEL": str(marker), "RECON_OUT_DIR": str(output),
           "BBASM_SKIP_HISTORICAL": "1",  # This test covers active toggles, never provider traffic.
           "BBASM_SKIP_NMAP": "1", "BBASM_SKIP_HTTPX": "1",
           "BBASM_SKIP_ACTIVE_CRAWL": "1", "BBASM_SKIP_NUCLEI": "1"}
    subprocess.run(["bash", "-c", wrapper, "bbasm-test", str(script), str(targets), "--quick"], env=env, check=True, timeout=30, capture_output=True)
    assert not marker.exists()
    assert not (output / "ports/nmap_results.txt").exists()


def test_tc_run_2_real_child_process_group_cleanup(tmp_path):
    async def scenario():
        child_file = tmp_path / "child.pid"
        code = "import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(120)"
        process = await asyncio.create_subprocess_exec(sys.executable, "-c", code, str(child_file), start_new_session=True)
        try:
            async def ready():
                while not child_file.exists():
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(ready(), 5)
            child_pid = int(child_file.read_text())
            await stop_process_group(process, grace=0.2)
            # A reparented zombie is dead but can remain until PID 1 reaps it.
            status = Path(f"/proc/{child_pid}/status")
            assert not status.exists() or "State:\tZ" in status.read_text()
        finally:
            await stop_process_group(process, grace=0.2)
    asyncio.run(scenario())
