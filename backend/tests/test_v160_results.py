"""arc-bbp Strong #65 (FN2-FN4, CDN): read nmap/ffuf results as results, and say when they are partial."""
import json

from backend.asm.phases import build_report, scan_root
from backend.asm.results import cdn_of, read_ffuf, read_nmap_greppable, read_nuclei_coverage, summarize_dirs, summarize_nuclei, summarize_ports
from backend.tests.p2_helpers import environment, write_output

GREP_DONE = """# Nmap 7.94 scan initiated Thu Oct 16 07:55:00 2026
Host: 104.18.1.10 (rpc.example.com)\tPorts: 80/open/tcp//http//Cloudflare http proxy/, 443/open/tcp//ssl|http//Cloudflare http proxy/, 1720/open/tcp//h323q931///, 8080/open/tcp//http-proxy//Cloudflare http proxy/\tIgnored State: filtered (996)
Host: 104.18.1.11 (drpc.example.com)\tPorts: 80/open/tcp//http//Cloudflare http proxy/, 5060/open/tcp//sip///, 8443/open/tcp//ssl|http//Cloudflare http proxy/, 2000/closed/tcp//cisco-sccp///\tIgnored State: filtered (995)
# Nmap done at Thu Oct 16 07:58:53 2026 -- 2 IP addresses (2 hosts up) scanned in 232.80 seconds
"""
GREP_CUT = "# Nmap 7.94 scan initiated\nHost: 192.0.2.7 (a.example.com)\tPorts: 22/open/tcp//ssh//OpenSSH 8.9/\tIgnored State: filtered (999)\n"


def test_every_host_and_port_is_read_not_just_the_last_port_of_each_line(tmp_path):
    path = tmp_path / "g.txt"
    path.write_text(GREP_DONE, encoding="utf-8")
    parsed = read_nmap_greppable(path)
    assert parsed["complete"] and parsed["hosts"] == 2 and len(parsed["pairs"]) == 7           # closed ports are not pairs
    assert {(p["host"], p["port"]) for p in parsed["pairs"]} >= {("rpc.example.com", 80), ("rpc.example.com", 1720), ("drpc.example.com", 5060)}
    path.write_text(GREP_CUT, encoding="utf-8")
    assert read_nmap_greppable(path)["complete"] is False                                       # no "# Nmap done" = stopped early


def test_unique_ports_and_host_port_pairs_are_different_numbers(tmp_path):
    for run, text in (("4", GREP_DONE), ("5", GREP_CUT)):
        write_output(tmp_path, f"{run}/ports/nmap_greppable.txt", text)
    summary = summarize_ports(tmp_path)
    assert summary["pairs"] == 8 and summary["hosts"] == 3 and summary["unique_ports"] == 7 and summary["complete"] is False
    assert [f["complete"] for f in summary["files"]] == [True, False]


def test_cloudflare_ports_are_labelled_as_cdn_ports_not_origin_ports(tmp_path):
    assert cdn_of("104.18.1.10") == "Cloudflare" and cdn_of("192.0.2.7") is None
    assert cdn_of("192.0.2.7", ["http Akamai edge"]) == "Akamai"
    write_output(tmp_path, "4/ports/nmap_greppable.txt", GREP_DONE)
    summary = summarize_ports(tmp_path)
    assert summary["cdn"] == ["Cloudflare"] and summary["cdn_pairs"] == 7 and sorted(summary["cdn_hosts"]) == ["drpc.example.com", "rpc.example.com"]


def ffuf_file(path, rows, **config):
    path.write_text(json.dumps({"commandline": "ffuf -u https://rpc.example.com/FUZZ", "config": config, "results": [
        {"input": {"FUZZ": name}, "status": status, "length": length, "words": words, "url": f"https://rpc.example.com/{name}", "host": "rpc.example.com"}
        for name, status, length, words in rows]}), encoding="utf-8")


def test_identical_block_pages_are_noise_and_403_is_never_a_hit(tmp_path):
    path = tmp_path / "ffuf_rpc.json"
    ffuf_file(path, [(f"p{i}", 403, 4547, 656) for i in range(24)] + [("admin", 200, 812, 40), ("api", 301, 0, 1)])
    item = read_ffuf(path)
    assert item["total"] == 26 and item["noise"] == 24
    assert item["noise_signature"] == [{"status": 403, "length": 4547, "words": 656, "count": 24}]
    assert [r["url"].rsplit("/", 1)[1] for r in item["significant"]] == ["admin", "api"]
    # a host that only ever answered 403
    only = tmp_path / "ffuf_only403.json"
    ffuf_file(only, [(f"q{i}", 403, 4547, 656) for i in range(9)])
    dirs_dir = tmp_path / "scan"
    write_output(dirs_dir, "4/dirs/ffuf_rpc.json", path.read_text())
    write_output(dirs_dir, "4/dirs/ffuf_only403.json", only.read_text())
    summary = summarize_dirs(dirs_dir)
    assert summary["total"] == 35 and summary["noise"] == 33 and summary["significant"] == 2
    assert summary["blocked_only"] == ["rpc.example.com"] or "rpc.example.com" in summary["blocked_only"]
    few = tmp_path / "ffuf_few.json"
    ffuf_file(few, [("a", 403, 100, 5), ("b", 403, 100, 5), ("c", 200, 300, 9)])
    assert read_ffuf(few)["noise"] == 0                                                         # three alike is a pattern, not yet noise


def test_run_report_counts_results_not_lines_and_flags_a_cut_off_nmap(settings):
    db, _, result = environment(settings, ["example.com"])
    root = scan_root(settings, _slug(db, result.scan_id), result.scan_id)
    write_output(root, "4/ports/nmap_greppable.txt", GREP_DONE)
    write_output(root, "5/ports/nmap_greppable.txt", GREP_CUT)
    write_output(root, "4/dirs/ffuf_rpc.json", (json.dumps({"results": [{"status": 403, "length": 4547, "words": 656, "host": "rpc.example.com", "url": f"https://rpc.example.com/{i}"} for i in range(24)]
                                                            + [{"status": 200, "length": 9, "words": 2, "host": "rpc.example.com", "url": "https://rpc.example.com/a"}]})))
    write_output(root, "monitors/takeover/subjack.txt", "[Not Vulnerable] a.example.com\n[Not Vulnerable] b.example.com\n[GEMFURY] c.example.com\n")
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='done_partial' WHERE id=?", (result.scan_id,))
    phases = {p["key"]: p for p in build_report(settings, db, result.scan_id)["phases"]}
    ports = phases["port_scan"]
    assert ports["status"] == "partial" and ports["count"] == 8 and "3 host" in ports["detail"] and "DỞ DANG" in ports["detail"]
    assert "Cloudflare" in ports["detail"] and "chưa chứng minh" in ports["detail"]
    dirs = phases["dir_fuzz"]
    assert dirs["status"] == "ran" and dirs["count"] == 1 and "24 giống hệt nhau" in dirs["detail"]
    takeover = phases["takeover"]
    assert takeover["count"] == 1 and "2 host đã kiểm và sạch" in takeover["detail"]           # 3 lines, 1 candidate


def _slug(db, scan_id):
    with db.connect() as conn:
        return conn.execute("SELECT p.slug FROM scan_run s JOIN program p ON p.id=s.program_id WHERE s.id=?", (scan_id,)).fetchone()[0]


def test_url_funnel_adds_up_to_what_the_table_shows(settings):
    """arc-bbp #65: "456 trong scope (đang xem)" while the table held 489 — the 33 URLs the HTTP probe answered on were not counted."""
    from backend.jobs.ingest import Ingester
    from backend.jobs.recon_orch import ReconOrchestrator
    db, _, result = environment(settings, ["*.example.com"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    out = plan.commands[0].output
    write_output(out, "subdomains/all.txt", "api.example.com\nwww.example.com\nshop.example.com\n")
    write_output(out, "live/urls.txt", "https://api.example.com\nhttps://www.example.com\nhttps://shop.example.com\n")
    write_output(out, "live/httpx_full.txt", "".join(f"https://{h}.example.com [200] [10] [T] [nginx]\n" for h in ("api", "www", "shop")))
    write_output(out, "urls/all.txt", "https://api.example.com/a\nhttps://api.example.com/a\nhttps://api.example.com/b\nhttps://evil.com/x\n")
    stats = Ingester(settings, db).ingest(plan)
    funnel = stats["url_funnel"]
    with db.connect() as conn:
        stored = conn.execute("SELECT count(*) FROM url WHERE last_seen_scan=?", (result.scan_id,)).fetchone()[0]
    assert funnel["stored"] == stored == stats["urls"]
    assert funnel["in_scope"] + funnel["from_probe"] == stored
    assert funnel["from_probe"] == 3 and funnel["in_scope"] == 2 and funnel["out_of_scope"] == 1


def test_auth_label_needs_an_endpoint_not_the_word_token_in_a_content_url():
    """arc-bbp #65: /arc-token-whitepaper, tokenization posts and /ecosystem/imtoken were labelled "đăng nhập"."""
    from backend.asm.urlintel import classify_url
    content = ["https://arc.io/arc-token-whitepaper", "https://arc.io/blog/what-is-tokenization", "https://arc.io/ecosystem/imtoken",
               "https://arc.io/blog/token-sale-faq", "https://arc.io/resetting-the-world", "https://arc.io/blog/passwords-are-dead"]
    for url in content:
        assert "auth" not in classify_url(url)[0], url
    endpoints = ["https://a.example.com/login", "https://a.example.com/api/v1/auth/login", "https://a.example.com/oauth/token",
                 "https://a.example.com/connect/token", "https://a.example.com/reset-password/abc123", "https://a.example.com/account/sign-in",
                 "https://a.example.com/user/forgot_password", "https://a.example.com/login.php", "https://a.example.com/verify-email",
                 "https://a.example.com/dang-nhap", "https://a.example.com/saml/callback", "https://a.example.com/Logout"]
    for url in endpoints:
        assert "auth" in classify_url(url)[0], url


# v1.6.1 (NUCLEI_COVERAGE_FOLLOWUP.md / V160_HOST_AUDIT.md "N"): stats.nuclei_templates only ever recorded the template
# set installed at launch (e.g. 14,036) — never what a run actually got through. recon_engine.sh Phase 9 now writes
# nuclei/coverage.json; these readers turn it into the same kind of honest "X/Y" numbers nmap/ffuf already get.
TRUNCATED_RUN = json.dumps({"live_urls": 60, "given_urls": 50, "limit": 50, "quick": True, "timed_out": False,
                            "last_stats": {"duration": "0:00:12", "errors": "3", "hosts": "50", "matched": "2", "percent": "100",
                                           "requests": "8200", "rps": "680", "startedAt": "2026-10-16T16:00:00Z", "templates": "120", "total": "8200"}})
TIMED_OUT_RUN = json.dumps({"live_urls": 2, "given_urls": 2, "limit": 200, "quick": False, "timed_out": True, "last_stats": None})


def test_read_nuclei_coverage_parses_the_engines_own_numbers(tmp_path):
    path = tmp_path / "coverage.json"
    path.write_text(TRUNCATED_RUN, encoding="utf-8")
    info = read_nuclei_coverage(path)
    assert info["live_urls"] == 60 and info["given_urls"] == 50 and info["limit"] == 50 and info["quick"] is True and info["timed_out"] is False
    assert info["templates"] == 120 and info["requests"] == 8200 and info["hosts"] == 50 and info["matched"] == 2 and info["percent"] == 100
    path.write_text(TIMED_OUT_RUN, encoding="utf-8")
    timed_out = read_nuclei_coverage(path)
    assert timed_out["timed_out"] is True and timed_out["templates"] is None             # killed before the first -stats-json tick
    assert read_nuclei_coverage(tmp_path / "missing.json") is None


def test_summarize_nuclei_merges_runs_and_counts_findings_separately_from_coverage(tmp_path):
    write_output(tmp_path, "4/nuclei/coverage.json", TRUNCATED_RUN)
    write_output(tmp_path, "4/nuclei/findings.jsonl", '{"template-id":"a"}\n{"template-id":"b"}\n')
    write_output(tmp_path, "5/nuclei/coverage.json", TIMED_OUT_RUN)
    write_output(tmp_path, "5/nuclei/findings.jsonl", '{"template-id":"c"}\n')
    summary = summarize_nuclei(tmp_path)
    assert summary["found"] and summary["findings"] == 3                                 # findings count, independent of coverage numbers
    assert summary["live_urls"] == 62 and summary["given_urls"] == 52 and summary["truncated"] is True   # one of the two runs was capped
    assert summary["timed_out"] is True                                                  # the other run was cut by the timeout
    assert summary["templates"] == 120 and summary["requests"] == 8200 and summary["hosts"] == 50
    assert summarize_nuclei(tmp_path / "empty")["found"] is False


def test_run_report_shows_real_nuclei_coverage_not_the_installed_template_count(settings):
    db, _, result = environment(settings, ["example.com"])
    root = scan_root(settings, _slug(db, result.scan_id), result.scan_id)
    write_output(root, "4/nuclei/coverage.json", TRUNCATED_RUN)
    write_output(root, "4/nuclei/findings.jsonl", '{"template-id":"a"}\n{"template-id":"b"}\n')
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='done' WHERE id=?", (result.scan_id,))
    nuclei = {p["key"]: p for p in build_report(settings, db, result.scan_id)["phases"]}["nuclei"]
    assert nuclei["count"] == 2 and nuclei["status"] == "ran"                             # truncation alone is not "partial": it ran to completion
    assert "50/60 URL đang sống được đưa cho nuclei" in nuclei["detail"]
    assert "giới hạn 50 URL mỗi lượt" in nuclei["detail"] and "KHÔNG được quét" in nuclei["detail"]
    assert "120 template" in nuclei["detail"] and "8200 request" in nuclei["detail"]
    assert "ĐÃ CÀI" in nuclei["detail"]                                                   # tells it apart from stats.nuclei_templates


def test_run_report_flags_a_timed_out_nuclei_run_as_partial(settings):
    db, _, result = environment(settings, ["example.com"])
    root = scan_root(settings, _slug(db, result.scan_id), result.scan_id)
    write_output(root, "4/nuclei/coverage.json", TIMED_OUT_RUN)
    write_output(root, "4/nuclei/findings.jsonl", "")
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='done_partial' WHERE id=?", (result.scan_id,))
    nuclei = {p["key"]: p for p in build_report(settings, db, result.scan_id)["phases"]}["nuclei"]
    assert nuclei["status"] == "partial" and "DỞ DANG" in nuclei["detail"]


def test_run_report_falls_back_to_the_old_line_count_without_a_coverage_file(settings):
    """Scans from before v1.6.1 (or BBASM_SKIP_NUCLEI) have no coverage.json; behaviour must stay exactly what it was."""
    db, _, result = environment(settings, ["example.com"])
    root = scan_root(settings, _slug(db, result.scan_id), result.scan_id)
    write_output(root, "4/nuclei/findings.jsonl", '{"template-id":"a"}\n{"template-id":"b"}\n{"template-id":"c"}\n')
    with db.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='done' WHERE id=?", (result.scan_id,))
    nuclei = {p["key"]: p for p in build_report(settings, db, result.scan_id)["phases"]}["nuclei"]
    assert nuclei["count"] == 3 and nuclei["detail"] is None and nuclei["status"] == "ran"
