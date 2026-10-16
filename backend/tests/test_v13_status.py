"""Wolt P2: say WHY a step did not run (config / missing tool / timeout) and WHICH scan a brief belongs to."""
import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.brief.generator import BriefGenerator
from backend.jobs.runner import JobRunner
from backend.log_buffer import ReconLogParser
from backend.main import create_app
from backend.tests.p2_helpers import FakeEgress, FakeProcess, environment, stop_fake


def parser(settings, depth="light", **kw):
    settings.BBASM_BBROOT = __import__("backend.config", fromlist=["PROJECT_ROOT"]).PROJECT_ROOT / "vendor/claude-bug-bounty"
    return ReconLogParser(settings, SimpleNamespace(depth=depth, skip_ffuf=kw.get("skip_ffuf", False)))


def test_log_lines_are_tagged_by_cause_not_just_printed(settings, monkeypatch):
    light, strong = parser(settings), parser(settings, "strong")
    tag, = [light.parse("\x1b[33m[!] ffuf not installed or no live hosts — skipping directory fuzzing\x1b[0m")[1]["tag"]]
    assert tag == "skipped_config"                                                      # ffuf never runs below Strong: not "missing"
    _, payload = light.parse("[!] ffuf not installed or no live hosts — skipping directory fuzzing")
    assert "chỉ chạy ở Strong" in payload["message"] and "not installed" not in payload["message"]
    # classify() asks shutil.which(..., path=settings.tool_search_path()) to tell "ffuf missing" from "no live hosts
    # yet"; tool_search_path() always prepends /usr/local/bin (v160 host audit), so this must not depend on whether
    # the machine running the tests happens to have a real ffuf installed there.
    monkeypatch.setattr("backend.log_buffer.shutil.which", lambda *a, **kw: None)
    assert strong.parse("[!] ffuf not installed or no live hosts — skipping directory fuzzing")[1]["tag"] == "missing_tool"
    assert light.parse("[!] nmap skipped (BBASM)")[1] == {"message": "[!] nmap skipped theo cấu hình scan", "tag": "skipped_config"}
    assert light.parse("[!] Skipping amass (quick mode)")[1]["tag"] == "skipped_config"
    assert light.parse("[!] subfinder not installed — skipping")[1]["tag"] == "missing_tool"
    assert light.parse("[!] gau failed or timed out; keeping partial output")[1]["tag"] == "timeout"
    assert light.parse("[!] No live hosts — skipping config check")[1]["tag"] == "no_input"
    assert light.parse("[✓] Live hosts: 4")[1] == {"message": "[✓] Live hosts: 4"}      # ordinary lines are untouched


def test_only_tools_the_configuration_uses_are_reported_missing(settings):
    async def scenario():
        db, _, result = environment(settings, ["example.com"])
        runner = JobRunner(settings, db, process_factory=lambda c: asyncio.sleep(0, FakeProcess()), stopper=stop_fake, egress=FakeEgress())
        runner.orchestrator.missing_tools = lambda: ["ffuf", "amass", "nuclei", "dnsx"]
        try:
            await runner.submit(result.scan_id, result.config.model_copy(update={"depth": "light", "scan_timeout": 300}))
            await runner.queue.join()
            return runner.logs.replay(result.scan_id), runner.status(result.scan_id)
        finally:
            await runner.close()
    events, row = asyncio.run(scenario())
    by_tag = {}
    for event in events:
        by_tag.setdefault(event.get("tag"), []).append(event.get("message", ""))
    assert any("nuclei" in m for m in by_tag["missing_tool"]) and not any("ffuf" in m or "amass" in m for m in by_tag["missing_tool"])
    assert any("ffuf" in m for m in by_tag["not_needed"]) and any("amass" in m for m in by_tag["not_needed"])
    assert not any(e.get("level") == "warning" and "ffuf" in e.get("message", "") for e in events)       # no scary warning for an unused tool
    import json
    assert json.loads(row["stats_json"])["missing_needed"] == ["nuclei"]


def test_health_does_not_list_dnsx_and_marks_bbscope_optional(settings):
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/health").json()
    assert "dnsx" not in body["tools"] and not any("dnsx" in v for v in body["missing_by_depth"].values())
    assert "ffuf" not in body["missing_by_depth"]["light"] and "bbscope" in body["optional_tools"]


def test_the_phase_catalog_has_no_dnsx(settings):
    from backend.asm.phases import PHASES
    assert all("dnsx" not in phase["tools"] for phase in PHASES)


def test_brief_names_its_scan_and_what_was_not_reached(settings):
    stats = {"coverage": {"discovered": 720, "probed": 4, "unprobed": 716},
             "sources": [{"source": "web.archive.org", "status": "timeout", "seconds": 45}, {"source": "crt.sh", "status": "ok", "seconds": 3}],
             "stages": [{"label": "Probe host đã khám phá", "status": "timeout"}], "path_rule_hosts": {"wolt.com": ["/en/x"]}}
    text = BriefGenerator.coverage_lines(stats)
    assert "720 tìm thấy · 4 đã probe · 716 chưa probe (scan chưa đầy đủ)" in text
    assert "web.archive.org (quá thời gian)" in text and "crt.sh" not in text
    assert "Giai đoạn bị cắt: Probe host đã khám phá" in text and "wolt.com" in text
    assert BriefGenerator.coverage_lines({}) == ""


def test_a_running_scan_marks_the_old_brief_and_the_new_brief_replaces_the_marker(settings):
    db, _, result = environment(settings, ["example.com"])
    generator = BriefGenerator(settings, db)
    target = generator.target("example.com")
    target.mkdir(parents=True, exist_ok=True)
    brief = target / "AGENT_BRIEF.md"
    brief.write_text("# AGENT BRIEF — example.com\nScan 3 · light · done\n", encoding="utf-8")
    generator.set_banner("example.com", "⏳ Scan #7 (light) đang chạy.")
    assert brief.read_text().startswith("<!-- BBASM-RUN -->\n⏳ Scan #7") and "Scan 3 · light · done" in brief.read_text()
    generator.set_banner("example.com", "⚠ Scan #7 (light) thất bại.")                  # replaced, never stacked
    assert brief.read_text().count("BBASM-RUN -->") == 2 and "thất bại" in brief.read_text() and "đang chạy" not in brief.read_text()
    generator.set_banner("example.com", None)
    assert brief.read_text() == "# AGENT BRIEF — example.com\nScan 3 · light · done\n"


def test_runner_marks_the_brief_while_running_and_when_a_scan_is_cancelled(settings):
    async def scenario():
        db, _, result = environment(settings, ["example.com"])
        target = BriefGenerator(settings, db).target("example.com")
        target.mkdir(parents=True, exist_ok=True)
        (target / "AGENT_BRIEF.md").write_text("# AGENT BRIEF — example.com\nScan 1 · light · done\n", encoding="utf-8")
        seen = []

        async def factory(command):
            seen.append((target / "AGENT_BRIEF.md").read_text())
            return FakeProcess(hold=True)
        runner = JobRunner(settings, db, process_factory=factory, stopper=stop_fake, egress=FakeEgress())
        try:
            await runner.submit(result.scan_id, result.config.model_copy(update={"depth": "light", "scan_timeout": 300}))
            for _ in range(200):
                if seen:
                    break
                await asyncio.sleep(0.01)
            await runner.cancel(result.scan_id)
            return seen, (target / "AGENT_BRIEF.md").read_text(), result.scan_id
        finally:
            await runner.close()
    seen, after, scan_id = asyncio.run(scenario())
    assert f"Scan #{scan_id} (light) đang chạy" in seen[0] and "Scan 1 · light · done" in seen[0]
    assert f"Scan #{scan_id} (light) đã bị huỷ" in after
