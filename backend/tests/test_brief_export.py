import io
import json
import tracemalloc
import zipfile

from fastapi.testclient import TestClient
import pytest

from backend.brief.export import build_export
from backend.brief.generator import BriefGenerator, USER_START, USER_END
from backend.jobs.scope_resolver import ScopeError
from backend.main import create_app
from backend.tests.p2_helpers import environment, write_output


def prepared(settings, depth="light", status="done"):
    db, _, result = environment(settings, ["*.example.com", "app:com.example.app"])
    with db.connect() as conn, conn:
        scan = conn.execute("SELECT * FROM scan_run").fetchone()
        stats = json.loads(scan["stats_json"])
        stats.update(subs=30, live=30, urls=10, findings=7)
        conn.execute("UPDATE scan_run SET status=?,depth=?,stats_json=?", (status, depth, json.dumps(stats)))
        for i in range(30):
            conn.execute("INSERT INTO asset(program_id,host,status_code,tech_json,first_seen_scan,last_seen_scan,state,rank_score) VALUES(?, ?,200,'[\"GraphQL\"]',?,?,'active',7)",
                         (scan["program_id"], f"api{i}.example.com", scan["id"], scan["id"]))
        for i in range(7):
            conn.execute("INSERT INTO finding(program_id,type,severity,name,first_seen_scan,last_seen_scan) VALUES(?,?,'high',?,?,?)",
                         (scan["program_id"], "nuclei" if i < 5 else "takeover", f"finding-{i}", scan["id"], scan["id"]))
    return db, result, BriefGenerator(settings, db)


def test_brief_sections_budget_real_counts_and_durable_program(settings):
    db, result, gen = prepared(settings)
    output = gen.generate(result.slug)
    path = gen.target(result.slug)
    text = (path / "AGENT_BRIEF.md").read_text(encoding="utf-8")
    assert output["bytes"] == len(text.encode()) < 12000
    for section in ("SCOPE", "SỐ LIỆU", "TOP SURFACE", "ASSET MỚI", "SIGNALS", "HƯỚNG TEST", "CÁCH LÀM VIỆC"):
        assert "## " + section in text
    assert "*.example.com" in text and "Manual [mobile]" in text
    assert "Assets: 30" in text and "Findings: 7" in text
    assert len([line for line in text.splitlines() if line.startswith("|api")]) == 25
    assert "{{" not in text and "TODO" not in text
    gen.update_program(result.slug, "Keep my auth notes")
    write_output(path, "notes/session.md", "my work")
    gen.generate(result.slug)
    assert "Keep my auth notes" in (path / "PROGRAM.md").read_text(encoding="utf-8")
    assert (path / "notes/session.md").read_text() == "my work"
    assert "mobile" in (path / "PROGRAM.md").read_text(encoding="utf-8")
    with pytest.raises(ScopeError):
        gen.update_program(result.slug, USER_START + "injected")


def test_passive_brief_has_degraded_warning(settings):
    _, result, gen = prepared(settings, "passive")
    gen.generate(result.slug)
    text = (gen.target(result.slug) / "AGENT_BRIEF.md").read_text(encoding="utf-8")
    assert "Depth=passive: chưa probe live/tech" in text
    assert "GraphQL" not in text


@pytest.mark.parametrize("include_recon", [True, False])
def test_zip_layout_manifest_and_partial(settings, include_recon):
    _, result, gen = prepared(settings, status="done_partial")
    gen.generate(result.slug)
    root = gen.target(result.slug)
    write_output(root, "recon/scans/1/0/result.txt", "data")
    write_output(root, ".env", "SYSTEM_SECRET")
    write_output(root, "notes/ignore.tmp", "junk")
    zip_path, name = build_export(gen, result.slug, include_recon)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            prefix = result.slug + "/"
            for filename in ("PROGRAM.md", "AGENT_BRIEF.md", "CLAUDE.md", ".scope", "audit.jsonl", "MANIFEST.json", "findings/", "reports/", "notes/"):
                assert prefix + filename in names
            assert (prefix + "recon/scans/1/0/result.txt" in names) is include_recon
            assert not any(n.endswith((".env", ".tmp")) for n in names)
            manifest = json.loads(archive.read(prefix + "MANIFEST.json"))
            assert manifest["scan_id"] == result.scan_id
            assert "*.example.com" in manifest["scope"]["in"]
            assert {"PROGRAM.md", "AGENT_BRIEF.md"} <= set(manifest["files"])
            assert manifest["stats"]["subs"] == 30
            assert name.startswith("bbasm-")
    finally:
        zip_path.unlink()


def test_zip_200mb_uses_bounded_memory(settings):
    _, result, gen = prepared(settings)
    gen.generate(result.slug)
    large = gen.target(result.slug) / "recon/large.bin"
    with large.open("wb") as stream:
        stream.truncate(200 * 1024 * 1024)
    tracemalloc.start()
    path, _ = build_export(gen, result.slug)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    path.unlink()
    assert peak < 20 * 1024 * 1024


def test_brief_program_export_api(settings):
    _, result, gen = prepared(settings)
    with TestClient(create_app(settings)) as client:
        base = f"/api/programs/{result.slug}"
        assert client.post(base + "/brief").status_code == 200
        assert client.get(base + "/brief").headers["content-type"].startswith("text/markdown")
        assert client.put(base + "/program", json={"content": "User note"}).status_code == 200
        assert "User note" in client.get(base + "/program").text
        response = client.get(base + "/export?include_recon=false")
        assert response.headers["content-type"] == "application/zip"
        assert zipfile.is_zipfile(io.BytesIO(response.content))


def test_oversized_scope_fails_explicitly(settings):
    db, result, gen = prepared(settings)
    with db.connect() as conn, conn:
        stats = json.loads(conn.execute("SELECT stats_json FROM scan_run").fetchone()[0])
        stats["resolved_scope"] *= 500
        conn.execute("UPDATE scan_run SET stats_json=?", (json.dumps(stats),))
    with pytest.raises(ScopeError, match="12KB"):
        gen.generate(result.slug)
