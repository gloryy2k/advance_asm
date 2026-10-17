"""Every function must say what it does, whether it ran, and where its output can be read."""
import json
import os

from fastapi.testclient import TestClient
import pytest

from backend.asm.phases import PHASES, redact
from backend.jobs.recon_orch import ReconOrchestrator
from backend.main import create_app
from backend.models import ScanConfig
from backend.tests.p2_helpers import environment, write_output


def scan_with_output(settings, depth="light", **flags):
    db, _, result = environment(settings, ["vuihoc.vn"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    out = plan.commands[0].output
    write_output(out, "subdomains/all.txt", "vuihoc.vn\nwww.vuihoc.vn\n")
    write_output(out, "live/httpx_full.txt", "https://vuihoc.vn [200] [1] [T] [nginx]\n")
    write_output(out, "urls/gau.txt", "https://vuihoc.vn/a\nhttps://vuihoc.vn/b\nhttps://vuihoc.vn/c\n")
    write_output(out, "nuclei/findings.jsonl", "")  # ran, found nothing
    write_output(out, "js/endpoints.txt", "/api/x\n")
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='done',depth=?", (depth,))
        conn.execute("UPDATE scan_config SET depth=?,skip_nmap=?,skip_nuclei=?,skip_active_crawl=?", (
            depth, flags.get("skip_nmap", 1), flags.get("skip_nuclei", 0), flags.get("skip_active_crawl", 0)))
        stats = json.loads(conn.execute("SELECT stats_json FROM scan_run").fetchone()[0])
        stats["missing_tools"] = flags.get("missing", ["katana"])
        conn.execute("UPDATE scan_run SET stats_json=?", (json.dumps(stats),))
    return db, result, plan


def test_catalog_is_complete_and_every_step_names_its_output():
    keys = [p["key"] for p in PHASES]
    assert len(keys) == len(set(keys)) == 12
    for p in PHASES:
        assert p["what"] and p["files"] and p["count_label"] and p["view"]["kind"] in {"hosts", "urls", "findings", "file"}


def test_tc_ph_1_status_is_derived_from_evidence_and_config_not_guessed(settings):
    db, result, _ = scan_with_output(settings, "light")
    with TestClient(create_app(settings)) as client:
        report = client.get(f"/api/scans/{result.scan_id}/phases").json()
    phases = {p["key"]: p for p in report["phases"]}
    assert phases["subdomain_enum"]["status"] == "ran" and phases["subdomain_enum"]["count"] == 2
    assert phases["live_probe"]["count"] == 1
    assert phases["url_history"]["count"] == 3 and phases["url_history"]["files"][0]["lines"] == 3
    assert phases["nuclei"]["status"] == "empty" and "không có nghĩa là an toàn" in phases["nuclei"]["reason"]
    assert phases["port_scan"]["status"] == "skipped" and "Strong" in phases["port_scan"]["reason"]
    assert phases["url_crawl"]["status"] == "missing_tool" and "katana" in phases["url_crawl"]["reason"]
    assert phases["dir_fuzz"]["status"] == "skipped"
    assert phases["takeover"]["status"] in {"no_output", "missing_tool"}
    assert phases["js_analysis"]["status"] == "ran"
    assert report["missing_tools"] == ["katana"]


def test_passive_skips_every_target_touching_step_with_the_reason(settings):
    db, result, _ = scan_with_output(settings, "passive", skip_nmap=1, skip_nuclei=1, skip_active_crawl=1)
    with TestClient(create_app(settings)) as client:
        phases = {p["key"]: p for p in client.get(f"/api/scans/{result.scan_id}/phases").json()["phases"]}
    # live_probe wrote a file in this fixture, so evidence wins over config; untouched steps are "skipped".
    for key in ("url_crawl", "config_expose", "takeover", "secrets", "port_scan"):
        assert phases[key]["status"] == "skipped", key
    assert "Passive" in phases["url_crawl"]["reason"]
    assert all(not p["touches"] for p in phases.values() if p["key"] in {"subdomain_enum", "url_history", "param_discover"})


def test_tc_ph_2_artifact_viewer_pages_filters_and_rejects_escape(settings, tmp_path):
    db, result, plan = scan_with_output(settings)
    rel = "0/urls/gau.txt"
    with TestClient(create_app(settings)) as client:
        base = f"/api/scans/{result.scan_id}"
        page = client.get(base + "/artifact", params={"path": rel, "limit": 2}).json()
        assert page["total"] == 3 and page["lines"] == ["https://vuihoc.vn/a", "https://vuihoc.vn/b"]
        assert client.get(base + "/artifact", params={"path": rel, "offset": 2}).json()["lines"] == ["https://vuihoc.vn/c"]
        found = client.get(base + "/artifact", params={"path": rel, "q": "/B"}).json()
        assert found["total"] == 1 and found["filtered"] is True
        for bad in ("../../../../etc/passwd", "/etc/passwd", "0/../../../../.scope", "nope.txt", "0/urls", "0/urls/../../../audit.jsonl"):
            denied = client.get(base + "/artifact", params={"path": bad})
            assert denied.status_code == 422 and denied.json()["error"]["code"] == "artifact_unavailable", bad
        link = plan.root / "0" / "urls" / "evil.txt"
        os.symlink("/etc/hostname", link)
        assert client.get(base + "/artifact", params={"path": "0/urls/evil.txt"}).status_code == 422  # symlinks never followed
        download = client.get(base + "/artifact/download", params={"path": rel})
        assert download.status_code == 200 and "attachment" in download.headers["content-disposition"]
        assert client.get(base + "/artifact/download", params={"path": "../x"}).status_code == 422


def test_secret_values_are_hidden_in_the_viewer_unless_revealed(settings):
    db, result, plan = scan_with_output(settings)
    secret = "AKIAIOSFODNN7EXAMPLE1234567890"
    write_output(plan.root, "monitors/secret/trufflehog.jsonl", json.dumps({"DetectorName": "AWS", "Raw": secret, "Verified": False}) + "\n")
    write_output(plan.root, "monitors/secret/regex_hits.txt", f"x.js: token={secret}\n")
    with TestClient(create_app(settings)) as client:
        base = f"/api/scans/{result.scan_id}/artifact"
        shown = client.get(base, params={"path": "monitors/secret/trufflehog.jsonl"}).json()
        assert secret not in json.dumps(shown) and shown["redacted"] is True and '"DetectorName": "AWS"' in shown["lines"][0]
        assert secret not in client.get(base, params={"path": "monitors/secret/regex_hits.txt"}).text
        assert secret in client.get(base, params={"path": "monitors/secret/trufflehog.jsonl", "reveal": "true"}).text
    assert redact("plain line", "gau.txt") == "plain line"


def test_phase_catalog_endpoint_and_unknown_scan(settings):
    with TestClient(create_app(settings)) as client:
        catalog = client.get("/api/meta/phases").json()
        assert [c["key"] for c in catalog][:3] == ["subdomain_enum", "live_probe", "port_scan"]
        environment(settings)
        assert client.get("/api/scans/999/phases").status_code == 422


def test_tool_defaults_endpoint_reflects_the_running_server_settings(settings):
    """A blank nmap/ffuf/nuclei/deep_hosts field in ScanConfig means 'use the server's current setting' -- the
    editor needs the real number to show, not just the word 'mặc định' (default), and it must track a server
    admin's own override rather than a number baked into the frontend."""
    settings.BBASM_NMAP_TIMEOUT, settings.BBASM_FFUF_MAXTIME = 111, 222
    settings.BBASM_NUCLEI_TIMEOUT, settings.BBASM_DEEP_HOSTS = 333, 44
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/meta/tool-defaults").json() == {
            "nmap_timeout": 111, "ffuf_maxtime": 222, "nuclei_timeout": 333, "deep_hosts": 44}


def test_tc_ph_3_plan_preview_follows_the_config_before_anything_runs(settings, monkeypatch):
    from backend.jobs.recon_orch import ReconOrchestrator as RO
    monkeypatch.setattr(RO, "missing_tools", lambda self: ["katana", "nuclei"])
    base = dict(depth="light", threads=50, rate_limit=150, scan_timeout=900, nuclei_severity="low", skip_nmap=True,
                skip_nuclei=False, skip_active_crawl=False, categories_enabled=["web"])
    with TestClient(create_app(settings)) as client:
        def plan(**over):
            return {p["key"]: p for p in client.post("/api/meta/plan", json={**base, **over}).json()["phases"]}
        light = plan()
        assert light["live_probe"]["status"] == "on" and light["port_scan"]["status"] == "off"
        assert light["nuclei"]["status"] == "missing_tool" and "nuclei" in light["nuclei"]["reason"]
        assert light["url_crawl"]["status"] == "missing_tool"
        assert plan(skip_historical=True)["url_history"]["status"] == "off"
        assert plan(skip_takeover=True)["takeover"]["status"] == "off" and plan(skip_secrets=True)["secrets"]["status"] == "off"
        passive = plan(depth="passive", scan_timeout=300, skip_nuclei=True, skip_active_crawl=True)
        assert passive["live_probe"]["status"] == "off" and passive["subdomain_enum"]["status"] == "on"
        strong = plan(depth="strong", scan_timeout=2700, skip_nmap=False)
        assert strong["port_scan"]["status"] in {"on", "missing_tool"} and strong["dir_fuzz"]["status"] in {"on", "missing_tool"}
        assert client.post("/api/meta/plan", json={**base, "threads": 999}).status_code == 422
        # "forced" tells the UI which switches are pointless: off because of the depth, not because the user said so.
        assert light["port_scan"]["forced"] is True and light["dir_fuzz"]["forced"] is True
        assert light["nuclei"]["forced"] is False and plan(skip_nuclei=True)["nuclei"]["forced"] is False
        assert plan(depth="passive", scan_timeout=300)["url_crawl"]["forced"] is True
        assert strong["port_scan"]["forced"] is False and strong["dir_fuzz"]["forced"] is False


def test_f1_credentials_are_hidden_in_any_file_viewer_search_and_default_download(settings):
    db, result, plan = scan_with_output(settings)
    marker = "hunter2-very-secret-value"
    write_output(plan.root, "notes/anything.txt", f"H1_TOKEN={marker}\nAuthorization: Bearer {marker}\nplain recon line\n"
                 "https://a.com/p?token=public-looking&x=1\n")
    with TestClient(create_app(settings)) as client:
        base = f"/api/scans/{result.scan_id}/artifact"
        shown = client.get(base, params={"path": "notes/anything.txt"}).json()
        assert marker not in json.dumps(shown) and shown["redacted"] is True
        assert "plain recon line" in shown["lines"] and "https://a.com/p?token=public-looking&x=1" in shown["lines"]  # URLs are recon data
        assert client.get(base, params={"path": "notes/anything.txt", "q": "hunter2"}).json()["total"] == 0  # cannot be found by guessing
        assert marker not in client.get(base + "/download", params={"path": "notes/anything.txt"}).text
        assert marker in client.get(base + "/download", params={"path": "notes/anything.txt", "reveal": "true"}).text
        assert marker in client.get(base, params={"path": "notes/anything.txt", "reveal": "true"}).text
