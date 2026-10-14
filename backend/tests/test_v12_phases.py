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
