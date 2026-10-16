"""Tool inventory: one table behind /api/health, /api/tools and the Review warnings."""
import stat

from fastapi.testclient import TestClient

from backend.api.health import DEPTH_TOOLS as HEALTH_DEPTH_TOOLS
from backend.asm.phases import PHASES
from backend.main import create_app
from backend.tools import DEPTH_TOOLS, OPTIONAL_TOOLS, TOOLS, phases_using


def test_every_tool_a_step_names_is_described_and_depths_stay_what_health_says():
    named = {tool for phase in PHASES for tool in phase["tools"]}
    assert named <= set(TOOLS), named - set(TOOLS)
    assert HEALTH_DEPTH_TOOLS is DEPTH_TOOLS
    assert DEPTH_TOOLS["passive"] == ["subfinder", "gau"] and "nuclei-templates" in DEPTH_TOOLS["light"] and DEPTH_TOOLS["strong"][-3:] == ["nmap", "ffuf", "amass"]
    assert set(OPTIONAL_TOOLS).isdisjoint(set(sum(DEPTH_TOOLS.values(), [])))        # optional means no depth needs it
    assert [p["key"] for p in phases_using("ffuf")] == ["dir_fuzz"]


def test_inventory_states_impact_and_agreement_with_health(monkeypatch, settings, tmp_path):
    settings.tools_dir.mkdir(parents=True)
    settings.tool_path("recon_engine.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    script = tmp_path / "httpx"
    script.write_text("#!/usr/bin/python3\n")
    present = {"bash": "/bin/bash", "nuclei": "/bin/nuclei", "httpx": str(script)}
    for module in ("backend.api.health.shutil", "backend.tools.shutil"):
        monkeypatch.setattr(module + ".which", lambda name, **kw: present.get(name))
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/tools").json()
        health = client.get("/api/health").json()
    rows = {r["id"]: r for r in body["tools"]}
    assert rows["bash"]["state"] == "ready" and rows["nuclei"]["state"] == "ready"
    assert rows["httpx"]["state"] == "wrong_binary" and "Python" in rows["httpx"]["detail"]
    assert rows["katana"]["state"] == "missing_binary" and rows["katana"]["remedy"]
    assert rows["nuclei-templates"]["state"] == "missing_data" and rows["nuclei-templates"]["required_for"] == ["light", "strong"]
    assert rows["nuclei-templates"]["impact"]["light"].startswith("Bước bị bỏ qua: Nuclei")
    assert rows["bbscope"]["optional"] and rows["bbscope"]["state"] == "missing_binary" and rows["bbscope"]["impact"]["light"] == "optional"
    assert rows["recon_engine.sh"]["state"] == "ready" and rows["secrets_hunter.sh"]["state"] == "missing_data"
    assert "bbscope" in body["summary"]["missing_optional"] and "bbscope" not in body["summary"]["missing_required"]
    assert "katana" in body["summary"]["missing_required"]
    for name, ready in health["tools"].items():        # /api/health and /api/tools never disagree
        if name in rows:
            assert (rows[name]["state"] == "ready") == ready, name


def test_deep_check_runs_version_only_on_request_and_caches_it(monkeypatch, settings, tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    for name, text in (("nuclei", "echo 'Nuclei Engine Version: v3.11.1' >&2"), ("katana", "echo 'v1.8.0'; exit 0")):
        path = fake / name
        path.write_text(f"#!/bin/sh\n{text}\n")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{fake}:/usr/bin:/bin")
    with TestClient(create_app(settings)) as client:
        before = {r["id"]: r for r in client.get("/api/tools").json()["tools"]}
        assert before["nuclei"]["version"] is None and before["nuclei"]["pinned_version"]      # the pinned one is known offline
        after = {r["id"]: r for r in client.post("/api/tools/check").json()["tools"]}
        assert after["nuclei"]["version"] == "v3.11.1" and after["katana"]["version"] == "v1.8.0" and after["nuclei"]["checked_at"]
        again = {r["id"]: r for r in client.get("/api/tools").json()["tools"]}
        assert again["nuclei"]["version"] == "v3.11.1"                                          # remembered without running anything
