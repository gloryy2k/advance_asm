"""User-run Docker build/runtime check; disabled even in integration unless opted in."""
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.environ.get("BBASM_DOCKER_TESTS") != "1", reason="Set BBASM_DOCKER_TESTS=1 on a Docker host")]


def test_docker_build_health_and_static_dashboard():
    root = Path(__file__).resolve().parents[2]
    name = "bbasm-acceptance-" + uuid4().hex[:12]
    subprocess.run(["docker", "build", "-t", name, "."], cwd=root, check=True, timeout=3600)
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
        assert all(health["tools"][name] for name in ("bash", "subfinder", "httpx", "nuclei", "gau", "nmap"))
        with urlopen(base, timeout=3) as response:
            assert b'root' in response.read()
    finally:
        if container:
            subprocess.run(["docker", "rm", "-f", container], check=False)
        subprocess.run(["docker", "image", "rm", name], check=False)
