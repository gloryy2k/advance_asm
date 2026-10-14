"""V7 export modes and V4 scope/policy verification labels."""
import io
import json
import zipfile

from fastapi.testclient import TestClient

from backend.brief.export import build_export
from backend.main import create_app
from backend.tests.p2_helpers import write_output
from backend.tests.test_brief_export import prepared


def zip_of(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        return names, {n: archive.read(n).decode("utf-8", "replace") for n in names if not n.endswith("/")}


def test_tc_exp_7_filtered_export_drops_out_of_scope_lines_and_says_so(settings):
    _, result, gen = prepared(settings)
    root = gen.target(result.slug)
    gen.generate(result.slug)
    write_output(root, "recon/scans/1/0/urls/all.txt",
                 "https://api.example.com/v1/x\nhttps://evil.com/steal\nhttp://other.org:8080/a\nwww.example.com\nheader without host\n")
    write_output(root, "recon/scans/1/0/live/httpx_full.txt", "https://evil.com [200]\nhttps://app.example.com [200]\n")
    path, name = build_export(gen, result.slug, True, "filtered")
    names, files = zip_of(path)
    assert name.endswith("-filtered.zip")
    text = files[f"{result.slug}/recon/scans/1/0/urls/all.txt"]
    assert "api.example.com/v1/x" in text and "www.example.com" in text and "header without host" in text
    assert "evil.com" not in text and "other.org" not in text
    assert "evil.com" not in files[f"{result.slug}/recon/scans/1/0/live/httpx_full.txt"]
    manifest = json.loads(files[f"{result.slug}/MANIFEST.json"])
    assert manifest["recon"]["mode"] == "filtered" and manifest["recon"]["lines_dropped"] == 3
    assert manifest["recon"]["raw_includes_out_of_scope"] is False
    assert "gate-audit" not in " ".join(names) and "evil.com" not in files[f"{result.slug}/audit.jsonl"]  # export leaves no trace in the audit
    path.unlink()


def test_full_export_is_labelled_raw_and_brief_has_no_recon(settings):
    _, result, gen = prepared(settings)
    gen.generate(result.slug)
    write_output(gen.target(result.slug), "recon/scans/1/0/urls/all.txt", "https://evil.com/x\n")
    full, name = build_export(gen, result.slug, True, "full")
    names, files = zip_of(full)
    assert "evil.com" in files[f"{result.slug}/recon/scans/1/0/urls/all.txt"] and not name.endswith("-full.zip")
    manifest = json.loads(files[f"{result.slug}/MANIFEST.json"])
    assert manifest["recon"]["raw_includes_out_of_scope"] is True and "THÔ" in manifest["recon"]["note"]
    brief, _ = build_export(gen, result.slug, True, "brief")
    assert not any("/recon/" in n for n in zip_of(brief)[0])
    full.unlink()
    brief.unlink()


def test_export_api_defaults_to_filtered_and_validates_mode(settings):
    _, result, gen = prepared(settings)
    gen.generate(result.slug)
    with TestClient(create_app(settings)) as client:
        base = f"/api/programs/{result.slug}/export"
        assert "-filtered" in client.get(base).headers["content-disposition"]
        assert "-brief" in client.get(base + "?mode=brief").headers["content-disposition"]
        assert "-brief" in client.get(base + "?include_recon=false").headers["content-disposition"]
        assert "-filtered" not in client.get(base + "?include_recon=true").headers["content-disposition"]  # explicit legacy flag = raw
        assert client.get(base + "?mode=bogus").status_code == 422


def test_tc_h1v_trust_levels_and_where_they_appear(settings):
    from backend.trust import scope_trust
    pub = scope_trust("h1", "verisk_vdp", {"policy_source": "public_dump", "policy_text": ""})
    assert pub["verified"] is False and pub["level"] == "public" and "CHƯA XÁC MINH" in pub["label"]
    assert "policy đầy đủ" in pub["missing"] and pub["official_url"] == "https://hackerone.com/verisk_vdp" and len(pub["checklist"]) == 3
    assert scope_trust("h1", "verisk_vdp", {"policy_source": "public_dump", "user_policy_text": "đã dán"})["missing"] == ["xác nhận scope hiện hành"]
    api = scope_trust("h1", "acme", {"policy_source": "api", "policy_text": "No DoS"})
    assert api["verified"] is True and api["missing"] == []
    assert scope_trust("h1", "acme", {"policy_source": "api", "policy_text": ""})["missing"] == ["policy"]
    raw = scope_trust("raw", None, {})
    assert raw["level"] == "manual" and raw["official_url"] is None


def test_unverified_h1_scope_is_labelled_in_review_program_md_and_brief(settings):
    import httpx
    from unittest.mock import Mock
    import subprocess
    from backend.brief.generator import BriefGenerator
    from backend.config import PROJECT_ROOT
    from backend.db import Database
    from backend.jobs.h1_scope import HackerOneScopeProvider
    from backend.jobs.scope_resolver import ScopeResolver
    from backend.models import ResolveRequest
    settings.BBASM_BBROOT = PROJECT_ROOT / "vendor/claude-bug-bounty"
    dump = [{"handle": "verisk_vdp", "targets": {"in_scope": [{"asset_identifier": "*.verisk.com", "asset_type": "WILDCARD"}], "out_of_scope": []}}]
    provider = HackerOneScopeProvider(settings, httpx.MockTransport(lambda r: httpx.Response(200, json=dump)),
                                      Mock(return_value=subprocess.CompletedProcess([], 0)))
    db = Database(settings.BBASM_DATA / "bbasm.db")
    db.migrate()
    result = ScopeResolver(settings, db, provider).resolve(ResolveRequest(input="https://hackerone.com/verisk_vdp?type=team"))
    with TestClient(create_app(settings)) as client:
        trust = client.get(f"/api/scans/{result.scan_id}/review").json()["trust"]
    assert trust["level"] == "public" and trust["verified"] is False
    generator = BriefGenerator(settings, db)
    generator.ensure_program(result.slug)
    program = (generator.target(result.slug) / "PROGRAM.md").read_text(encoding="utf-8")
    assert "CHƯA XÁC MINH" in program and "https://hackerone.com/verisk_vdp" in program
