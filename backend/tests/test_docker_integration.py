"""User-run Docker build/runtime check; disabled even in integration unless opted in."""
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.environ.get("BBASM_DOCKER_TESTS") != "1", reason="Set BBASM_DOCKER_TESTS=1 on a Docker host")]


def test_docker_build_health_and_static_dashboard(record_property):
    root = Path(__file__).resolve().parents[2]
    name = "bbasm-acceptance-" + uuid4().hex[:12]
    started = time.monotonic()
    subprocess.run(["docker", "build", "-t", name, "."], cwd=root, check=True, timeout=3600)
    seconds = round(time.monotonic() - started, 2)
    record_property("docker_build_seconds", seconds)
    print(f"Docker build completed in {seconds}s", flush=True)
    container = None
    try:
        container = subprocess.check_output(["docker", "run", "-d", "--rm", "--name", name,
            "-e", "BBASM_UPDATE_TEMPLATES=0", "-p", "127.0.0.1::8000", name], text=True).strip()
        port = subprocess.check_output(["docker", "port", container, "8000/tcp"], text=True).strip().split(":")[-1]
        base = "http://127.0.0.1:" + port
        for _ in range(30):
            try:
                with urlopen(base + "/api/health", timeout=3) as response:
                    health = json.load(response)
                break
            except OSError:
                time.sleep(2)
        else:
            pytest.fail("Container did not become healthy")
        assert health["ok"]
        assert all(health["tools"][name] for name in ("bash", "subfinder", "httpx", "nuclei", "gau", "nmap",
                                                     "dnsx", "katana", "amass", "ffuf", "trufflehog"))
        subprocess.run(["docker", "exec", container, "python", "-c",
            "from backend.config import Settings; import subprocess; s=Settings(); "
            "[subprocess.run(['bash','-n',str(s.tool_path(name))],check=True) "
            "for name in ('recon_engine.sh','scope_aggregator.sh')]"], check=True, timeout=30)
        # Unlike TestClient, this reaches uvicorn's actual WebSocket protocol.
        # Resolve only a local raw draft: no target traffic or recon launch.
        with urlopen(Request(base + "/api/scope/resolve", data=json.dumps({"input": "raw", "scope": ["127.0.0.1"]}).encode(),
                             headers={"Content-Type": "application/json"}), timeout=10) as response:
            draft = json.load(response)
        from websockets.sync.client import connect
        with connect(f"ws://127.0.0.1:{port}/ws/scan/{draft['scan_id']}", open_timeout=5) as websocket:
            assert websocket.response.status_code == 101
        with urlopen(base, timeout=3) as response:
            assert b'root' in response.read()
    finally:
        if container:
            subprocess.run(["docker", "rm", "-f", container], check=False)
        subprocess.run(["docker", "image", "rm", name], check=False)
