"""Opt-in checks for the Linux process and shell interfaces; never run in unit CI."""

import asyncio
import os
from pathlib import Path
import subprocess
import sys
import shutil
import psutil

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


@pytest.mark.parametrize("mode", ["cancel", "hard_timeout", "parent_exited"])
def test_tc_run_2_real_child_process_group_cleanup(tmp_path, mode):
    if not shutil.which("timeout") or not shutil.which("bash"):
        pytest.skip("GNU timeout and Bash required")
    async def scenario():
        child_file = tmp_path / "child.pid"
        code = "import os,signal,time,pathlib,sys; signal.signal(signal.SIGTERM,signal.SIG_IGN); pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(300)"
        wrapper = 'timeout 300 "$1" -c "$2" "$3" & while [ ! -s "$3" ]; do sleep 0.01; done; '
        wrapper += "exit 0" if mode == "parent_exited" else "wait"
        process = await asyncio.create_subprocess_exec("bash", "-c", wrapper, "bbasm-test", sys.executable, code, str(child_file), start_new_session=True)
        child = None
        try:
            async def ready():
                while not child_file.exists() or child_file.stat().st_size == 0:
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(ready(), 5)
            child_pid = int(child_file.read_text())
            child = psutil.Process(child_pid)
            assert os.getpgid(child_pid) != process.pid
            assert os.getsid(child_pid) == process.pid
            async def wait_with_cleanup():
                try:
                    await asyncio.Future()
                finally:
                    await stop_process_group(process, grace=0.2)
            if mode == "parent_exited":
                await asyncio.wait_for(process.wait(), 5)
                await stop_process_group(process, grace=0.2)
            elif mode == "hard_timeout":
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(wait_with_cleanup(), 0.1)
            else:
                task = asyncio.create_task(wait_with_cleanup())
                await asyncio.sleep(0)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            async def dead():
                while child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(dead(), 3)
        finally:
            await stop_process_group(process, grace=0.2)
            if child is not None:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
    asyncio.run(scenario())
