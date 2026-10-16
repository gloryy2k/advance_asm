"""Nuclei templates as a managed data set: atomic updates, failure keeps the old set, custom templates are checked."""
import json
import stat
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from backend.jobs.scope_resolver import ScopeError
from backend.main import create_app
from backend.templates import MARKER, TemplateStore, official_ready, selected_custom, snapshot_for_scan

GOOD = """id: my-check
info: {name: My check, author: me, severity: low}
http:
  - method: GET
    path: ["{{BaseURL}}/status"]
    matchers: [{type: status, status: [200]}]
"""
FAKE = """#!/bin/sh
# fake nuclei: -update-templates installs $FAKE_COUNT templates under $HOME/nuclei-templates; -validate checks nothing
[ -f "$(dirname "$0")/fake.env" ] && . "$(dirname "$0")/fake.env"
case "$*" in
  *-validate*) [ -n "$FAKE_VALIDATE_FAIL" ] && { echo "[ERR] bad template" >&2; exit 1; }; exit 0 ;;
  *-update-templates*)
    [ -n "$FAKE_SLEEP" ] && sleep "$FAKE_SLEEP"
    if [ "${FAKE_COUNT:-0}" -gt 0 ]; then
      mkdir -p "$HOME/nuclei-templates/http"
      i=0; while [ $i -lt "$FAKE_COUNT" ]; do echo "id: t$i" > "$HOME/nuclei-templates/http/t$i.yaml"; i=$((i+1)); done
      echo '{"nuclei-templates-version":"v9.9.9"}' > "$HOME/nuclei-templates/.templates-config.json"
    else
      echo "[WRN] failed to update nuclei templates: cause=\\"GET https://api.github.com/...: 403 rate limit exceeded\\"" >&2
    fi
    exit 0 ;;
esac
exit 0
"""


@pytest.fixture
def env(tmp_path, monkeypatch, settings):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    nuclei = bin_dir / "nuclei"
    nuclei.write_text(FAKE)
    nuclei.chmod(nuclei.stat().st_mode | stat.S_IEXEC)
    # Settings.tool_search_path() always prepends ~/go/bin, /opt/homebrew/bin and /usr/local/bin ahead of $PATH (to
    # match the vendored recon PATH), so setting $PATH alone does not isolate this fixture from a real nuclei the
    # test machine happens to have installed in one of those fixed directories (v160 host audit). Override the
    # method itself so only this fake binary is ever found.
    monkeypatch.setattr(type(settings), "tool_search_path", lambda self: f"{bin_dir}:/usr/bin:/bin")
    settings.BBASM_TEMPLATES_MIN = 3

    class Env:
        def __init__(self):
            self.values = {}

        def set(self, **kv):
            self.values.update({"FAKE_" + k.upper(): v for k, v in kv.items()})
            (bin_dir / "fake.env").write_text("".join(f"{k}={v}\n" for k, v in self.values.items()))
    return settings, Env()


def store_with(settings, fake, **values):
    fake.set(**values)
    return TemplateStore(settings)


def test_update_installs_atomically_and_describes_the_set(env):
    settings, monkeypatch = env
    store = store_with(settings, monkeypatch, count=5)
    assert not official_ready(settings) and store.describe()["installed"] is False
    job = store.start_update(background=False)
    assert job["state"] == "ok" and job["count"] == 5
    info = store.describe()
    assert info["installed"] and info["managed"] and info["count"] == 5 and info["version"] == "v9.9.9" and info["source"] == "projectdiscovery/nuclei-templates"
    marker = json.loads((settings.templates_dir / "official" / MARKER).read_text())
    assert marker["count"] == 5 and official_ready(settings)
    assert not (settings.templates_dir / "official.staging").exists() and not (settings.templates_dir / "update-home").exists()
    audit = (settings.BBASM_DATA / "audit.jsonl").read_text()
    assert "template_update" in audit
    # a second update keeps the previous set beside the new one
    monkeypatch.set(count="7")
    store.start_update(background=False)
    assert store.describe()["count"] == 7 and (settings.templates_dir / "official.prev").is_dir()


def test_a_failed_or_incomplete_update_keeps_the_old_set_and_says_why(env):
    settings, monkeypatch = env
    store = store_with(settings, monkeypatch, count=5)
    store.start_update(background=False)
    before = store.describe()
    monkeypatch.set(count="0")                    # nuclei warns and exits 0 without downloading anything
    job = store.start_update(background=False)
    assert job["state"] == "failed" and "rate limit" in job["message"].lower() and "giữ" in job["message"]
    monkeypatch.set(count="2")                    # fewer than the minimum: an incomplete download
    job = store.start_update(background=False)
    assert job["state"] == "failed" and "không đầy đủ" in job["message"]
    after = store.describe()
    assert after["count"] == before["count"] == 5 and after["installed"]            # the live set never changed
    assert not (settings.templates_dir / "official.staging").exists()


def test_update_timeout_and_single_flight_and_restart_recovery(env):
    settings, monkeypatch = env
    settings.BBASM_TEMPLATES_TIMEOUT = 10
    store = TemplateStore(settings, run=lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("nuclei", 10)))
    job = store.start_update(background=False)
    assert job["state"] == "failed" and "Quá thời gian" in job["message"]
    # a running job refuses a second start, and a restart turns a dead 'running' into 'failed'
    slow = store_with(settings, monkeypatch, count=5, sleep=2)
    slow.start_update(background=True)
    with pytest.raises(ScopeError) as err:
        slow.start_update(background=True)
    assert err.value.code == "template_update_running"
    for _ in range(100):
        time.sleep(0.1)
        if slow.describe()["job"]["state"] != "running":
            break
    assert slow.describe()["job"]["state"] == "ok"
    slow._set_job(state="running")
    TemplateStore(settings).recover()
    assert TemplateStore(settings).describe()["job"]["state"] == "failed"


def test_custom_templates_are_checked_stored_selected_and_removed(env):
    settings, monkeypatch = env
    store = store_with(settings, monkeypatch)
    entry = store.import_custom(GOOD.encode())
    assert entry["id"] == "my-check" and entry["protocols"] == ["http"] and (settings.templates_dir / "custom" / "my-check.yaml").is_file()
    with pytest.raises(ScopeError) as dup:
        store.import_custom(GOOD.encode())
    assert dup.value.code == "template_duplicate"
    bad = {
        "code protocol": GOOD.replace("http:", "code:\n  - engine: [sh]\n    source: id\nhttp:"),
        "javascript": GOOD.replace("http:", "javascript:\n  - code: 1\nhttp:"),
        "fixed absolute URL": GOOD.replace('"{{BaseURL}}/status"', '"https://other.example/x"'),
        "bad id": GOOD.replace("id: my-check", "id: ../evil"),
        "no protocol": "id: nothing\ninfo: {name: x}\n",
        "not a mapping": "- a\n- b\n",
        "too large": GOOD + "# " + "x" * 300_000,
        "tcp to a fixed host": "id: tcp-fixed\ninfo: {name: x}\ntcp:\n  - host: ['10.0.0.1:22']\n    inputs: [{data: hi}]\n",
        "raw absolute request line": "id: rawabs\ninfo: {name: x}\nhttp:\n  - raw:\n      - |\n        GET http://other.example/ HTTP/1.1\n        Host: other.example\n",
    }
    for label, text in bad.items():
        with pytest.raises(ScopeError) as err:
            store.import_custom(text.encode())
        assert err.value.code == "invalid_template", label
    monkeypatch.set(validate_fail="1")                        # nuclei -validate has the last word
    with pytest.raises(ScopeError):
        store.import_custom(GOOD.replace("my-check", "other-check").encode())
    assert not (settings.templates_dir / "custom" / "other-check.yaml").exists()
    assert selected_custom(settings, ["my-check", "missing", "../x"]) == [str(settings.templates_dir / "custom" / "my-check.yaml")]
    store.delete_custom("my-check")
    assert store.describe()["custom"] == [] and selected_custom(settings, ["my-check"]) == []


def test_scans_point_nuclei_at_the_managed_set_and_record_what_they_ran_with(env):
    from backend.jobs.recon_orch import nuclei_templates_ready, recon_env
    from backend.jobs.scope_resolver import default_config
    settings, monkeypatch = env
    store = store_with(settings, monkeypatch, count=5)
    config = default_config(settings, []).model_copy(update={"nuclei_custom": ["my-check"]})
    assert not nuclei_templates_ready(settings) and "BBASM_NUCLEI_OFFICIAL" not in recon_env(settings, config, settings.BBASM_DATA)
    store.start_update(background=False)
    store.import_custom(GOOD.encode())
    env_vars = recon_env(settings, config, settings.BBASM_DATA)
    assert nuclei_templates_ready(settings) and env_vars["BBASM_NUCLEI_OFFICIAL"].endswith("/official")
    assert env_vars["BBASM_NUCLEI_CUSTOM"].endswith("/custom/my-check.yaml")
    snap = snapshot_for_scan(settings, config)
    assert snap["official"]["count"] == 5 and snap["official"]["managed"] and snap["custom"] == ["my-check"]
    assert snapshot_for_scan(settings, config.model_copy(update={"depth": "passive"})) is None


def test_api_update_import_and_delete(env):
    settings, monkeypatch = env
    monkeypatch.set(count="4")
    settings.BBASM_UPDATE_TEMPLATES = "0"
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/tools/templates").json()["installed"] is False
        assert client.post("/api/tools/templates/update").status_code == 200
        for _ in range(100):
            time.sleep(0.1)
            if client.get("/api/tools/templates").json()["job"]["state"] != "running":
                break
        info = client.get("/api/tools/templates").json()
        assert info["job"]["state"] == "ok" and info["count"] == 4 and info["installed"]
        tools = {r["id"]: r for r in client.get("/api/tools").json()["tools"]}
        assert tools["nuclei-templates"]["state"] == "ready" and tools["nuclei-templates"]["templates"]["count"] == 4
        assert "installed" in client.get("/api/health").json()["tools"] or client.get("/api/health").json()["tools"]["nuclei-templates"] is True
        made = client.post("/api/tools/templates/custom", json={"content": GOOD})
        assert made.status_code == 200 and made.json()["id"] == "my-check"
        refused = client.post("/api/tools/templates/custom", json={"content": GOOD.replace("http:", "code:")})
        assert refused.status_code == 422 and refused.json()["error"]["code"] == "invalid_template"
        assert client.delete("/api/tools/templates/custom/my-check").status_code == 200
        assert client.delete("/api/tools/templates/custom/my-check").status_code == 422


def test_boot_updates_only_when_asked(env):
    settings, monkeypatch = env
    monkeypatch.set(count="4")
    settings.BBASM_UPDATE_TEMPLATES = "auto"
    with TestClient(create_app(settings)) as client:           # nothing installed yet: the first boot installs in the background
        for _ in range(100):
            time.sleep(0.1)
            if (client.get("/api/tools/templates").json()["job"] or {}).get("state") == "ok":
                break
        assert client.get("/api/tools/templates").json()["count"] == 4
    started = (settings.BBASM_DATA / "audit.jsonl").read_text().count("template_update")
    with TestClient(create_app(settings)):                     # installed already: auto does not download again
        time.sleep(0.3)
    assert (settings.BBASM_DATA / "audit.jsonl").read_text().count("template_update") == started
