"""What each recon step does, whether it ran, and where its output can be read.

This is the single source of truth the Run page, the Program › Lịch sử view and the Help page share,
so every function the dashboard offers has the same name, the same one-line explanation and a
pointer to its output. It only reads files already on disk; it never runs a tool.
"""
import glob
import json
import os
from pathlib import Path
import re

# kind: how the UI should open the output. "urls"/"hosts"/"findings" are structured views;
# "file" opens the raw artifact viewer.
PHASES = [
    {"key": "subdomain_enum", "title": "Tìm subdomain", "touches": False, "tools": ["subfinder", "amass"],
     "what": "Gom subdomain từ nguồn công khai (subfinder, amass, crt.sh, wayback). Không gửi request tới target.",
     "files": ["subdomains/all.txt"], "count_label": "host", "view": {"kind": "hosts", "label": "Xem danh sách host"}},
    {"key": "live_probe", "title": "Probe HTTP", "touches": True, "tools": ["httpx"],
     "what": "Hỏi từng host xem có phản hồi web không: mã trạng thái, tiêu đề, công nghệ (tech).",
     "files": ["live/httpx_full.txt", "live/urls.txt"], "count_label": "host phản hồi", "view": {"kind": "hosts", "label": "Xem host + trạng thái"}},
    {"key": "port_scan", "title": "Quét cổng", "touches": True, "tools": ["nmap"],
     "what": "nmap tìm cổng mở và dịch vụ. Chỉ chạy ở mức Strong.",
     "files": ["ports/nmap_greppable.txt", "ports/nmap_results.txt"], "count_label": "cặp host/cổng", "view": {"kind": "file", "label": "Đọc kết quả nmap"}},
    {"key": "url_history", "title": "URL lịch sử", "touches": False, "tools": ["gau"],
     "what": "Lấy URL cũ từ archive (gau, Wayback). Chỉ cho biết URL từng tồn tại — chưa phải đang chạy.",
     "files": ["urls/gau.txt", "urls/wayback.txt"], "count_label": "URL thô", "view": {"kind": "urls", "label": "Xem URL đã lọc scope"}},
    {"key": "url_crawl", "title": "Crawl chủ động", "touches": True, "tools": ["katana"],
     "what": "katana đi theo liên kết trên host đang chạy để tìm URL mới. Gửi nhiều request.",
     "files": ["urls/katana.txt"], "count_label": "URL", "view": {"kind": "urls", "label": "Xem URL đã crawl", "filter": {"verification": "observed"}}},
    {"key": "js_analysis", "title": "Phân tích JavaScript", "touches": True, "tools": ["curl"],
     "what": "Tải file JS, tìm endpoint ẩn và chuỗi giống khoá bí mật.",
     "files": ["js/endpoints.txt", "urls/js_files.txt", "js/potential_secrets.txt"], "count_label": "endpoint", "view": {"kind": "urls", "label": "Xem URL JS", "filter": {"tag": "js"}}},
    {"key": "dir_fuzz", "title": "Dò thư mục", "touches": True, "tools": ["ffuf"],
     "what": "ffuf thử danh sách đường dẫn phổ biến. Chỉ chạy ở mức Strong.",
     "files": ["dirs/*.json"], "count_label": "kết quả đáng xem", "view": {"kind": "file", "label": "Đọc kết quả ffuf"}},
    {"key": "config_expose", "title": "File cấu hình lộ", "touches": True, "tools": ["curl"],
     "what": "Kiểm tra vài file hay bị lộ (.env, config.js…) trên host đang chạy.",
     "files": ["exposure/config_files.txt"], "count_label": "file lộ", "view": {"kind": "file", "label": "Đọc danh sách"}},
    {"key": "param_discover", "title": "Tham số", "touches": False, "tools": [],
     "what": "Thống kê tham số query từ URL đã thu thập, đánh dấu tên hay gặp lỗi (id, redirect, file…).",
     "files": ["params/unique_params.txt", "params/interesting_params.txt"], "count_label": "tham số", "view": {"kind": "urls", "label": "Xem URL có tham số", "filter": {"tag": "params"}}},
    {"key": "nuclei", "title": "Nuclei", "touches": True, "tools": ["nuclei", "nuclei-templates"], "all_required": True,
     "what": "Chạy bộ mẫu kiểm tra lỗi đã biết theo mức nghiêm trọng bạn chọn, trên mọi URL đang sống (không giới hạn số URL/lượt). "
             "Có thể chạy lâu nếu scan có nhiều URL; bị cắt khi hết ngân sách thời gian của giai đoạn, Run báo rõ khi đó.",
     "files": ["nuclei/findings.jsonl", "nuclei/templates_loaded.txt"], "count_label": "finding", "view": {"kind": "findings", "label": "Xem findings", "filter": {"type": "nuclei"}}},
    {"key": "takeover", "title": "Takeover", "touches": True, "tools": ["subjack", "dnsreaper"],
     "what": "Tìm subdomain trỏ tới dịch vụ đã bị xoá (có thể bị chiếm).",
     "files": ["monitors/takeover/subjack.txt", "monitors/takeover/dnsreaper.json"], "count_label": "ứng viên", "view": {"kind": "findings", "label": "Xem findings", "filter": {"type": "takeover"}}},
    {"key": "secrets", "title": "Bí mật trong JS", "touches": True, "tools": ["trufflehog", "noseyparker"],
     "what": "Tải tối đa 100 file JS và quét khoá/token rò rỉ. Giá trị bí mật bị ẩn khi xem.",
     "files": ["monitors/secret/trufflehog.jsonl", "monitors/secret/regex_hits.txt", "monitors/secret/noseyparker.jsonl"], "count_label": "dấu vết", "view": {"kind": "findings", "label": "Xem findings", "filter": {"type": "secret"}}},
]
BY_KEY = {p["key"]: p for p in PHASES}
TEXT_SUFFIXES = {"", ".txt", ".json", ".jsonl", ".md", ".log", ".csv", ".xml", ".html"}
SECRET_FILES = {"trufflehog.jsonl", "noseyparker.jsonl", "gitleaks.json", "potential_secrets.txt", "regex_hits.txt", "dnsreaper.json"}
SECRET_KEYS = {"Raw", "RawV2", "Secret", "Match", "Redacted", "raw", "secret", "match"}
MAX_LINE = 2000
MAX_SCAN_BYTES = 300 * 1024 * 1024
MAX_COUNT_BYTES = 50 * 1024 * 1024


def disabled_reason(config, key, *, historical_off=False):
    """Why this step cannot have run, when the *reviewed configuration* says so; else None."""
    passive = config.depth == "passive"
    if key in {"live_probe", "url_crawl", "js_analysis", "config_expose", "nuclei", "takeover", "secrets"} and passive:
        return "Mức Passive không gửi request tới target"
    if key == "port_scan" and (passive or config.depth != "strong" or config.skip_nmap):
        return "Chỉ chạy ở mức Strong và khi không tắt nmap"
    if key == "dir_fuzz" and (passive or config.depth != "strong" or config.skip_active_crawl):
        return "Chỉ chạy ở mức Strong và khi không tắt crawl chủ động"
    if key in {"url_crawl", "js_analysis"} and config.skip_active_crawl:
        return "Bạn đã tắt crawl chủ động"
    if key == "nuclei" and config.skip_nuclei:
        return "Bạn đã tắt nuclei"
    if key == "url_history" and (historical_off or getattr(config, "skip_historical", False)):
        return "Nguồn lịch sử bị tắt"
    for flag, phase in (("skip_takeover", "takeover"), ("skip_secrets", "secrets")):
        if key == phase and getattr(config, flag, False):
            return "Bạn đã tắt bước này"
    return None


SKIP_FLAGS = ("skip_nmap", "skip_nuclei", "skip_active_crawl", "skip_ffuf", "skip_historical", "skip_takeover", "skip_secrets")


def plan_for(config, settings, missing_tools):
    """What a scan with this config WILL do, step by step — shown in Review before anything runs."""
    missing = set(missing_tools)
    # "forced" = off because of the depth itself; flipping the user's switch could not turn it on.
    neutral = config.model_copy(update={flag: False for flag in SKIP_FLAGS})
    out = []
    for phase in PHASES:
        reason = disabled_reason(config, phase["key"], historical_off=settings.BBASM_SKIP_HISTORICAL)
        absent = [t for t in phase["tools"] if t in missing]
        if reason:
            status = "off"
        elif phase["tools"] and (absent if phase.get("all_required") else len(absent) == len(phase["tools"])):
            status, reason = "missing_tool", "Thiếu " + ", ".join(absent) + " — bước này sẽ bị bỏ qua."
        else:
            status = "on"
        out.append({"key": phase["key"], "title": phase["title"], "what": phase["what"], "touches": phase["touches"],
                    "status": status, "reason": reason, "view": phase["view"],
                    "forced": disabled_reason(neutral, phase["key"], historical_off=settings.BBASM_SKIP_HISTORICAL) is not None})
    return out


def tools_needed(config, settings=None):
    """Tools of the steps this configuration will actually run: only a missing one of these deserves a warning."""
    historical_off = bool(settings and settings.BBASM_SKIP_HISTORICAL)
    needed = set()
    for phase in PHASES:
        if disabled_reason(config, phase["key"], historical_off=historical_off) is None:
            # The first tool of a step is its main one; the rest are alternatives (dnsreaper beside subjack) or only
            # used in full mode (amass runs below --quick, i.e. at Strong).
            needed.update(phase["tools"] if phase.get("all_required") else phase["tools"][:1])
            if phase["key"] == "subdomain_enum" and config.depth == "strong":
                needed.add("amass")
    return needed


def scan_root(settings, slug, scan_id):
    return (settings.BBASM_TARGETS / slug / "recon" / "scans" / str(scan_id)).resolve()


def _safe_files(root):
    if not root.is_dir() or root.is_symlink():
        return []
    result = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts) or "input" in rel.parts[:2] or "js_bundles" in rel.parts:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            result.append(path)
    return result


def count_lines(path):
    try:
        if path.stat().st_size > MAX_COUNT_BYTES:   # counting lines of a huge file just to show a number is not worth the I/O
            return None
        total, last = 0, b""
        with path.open("rb") as stream:
            while chunk := stream.read(1 << 20):
                total += chunk.count(b"\n")
                last = chunk[-1:]
        return total + (1 if last and last != b"\n" else 0)
    except OSError:
        return None


def structured_result(key, root):
    """For steps whose output is more than a list of lines: (count, detail, partial, data). None when the step has no reader.
    Reads files only. `partial` = the tool stopped before it finished, so the numbers cover only part of the targets."""
    from backend.asm import results
    from backend.asm.takeover import summarize
    if key == "port_scan":
        ports = results.summarize_ports(root)
        if not ports["found"]:
            return None
        detail = (f"{ports['hosts']} host, {ports['pairs']} cặp host/cổng mở ({ports['unique_ports']} số cổng khác nhau)"
                  + ("" if ports["complete"] else " — DỞ DANG: nmap dừng trước khi quét xong, chỉ gồm các host đã xong"))
        if ports["cdn"]:
            detail += (f". {ports['cdn_pairs']} cặp nằm trên IP của {', '.join(ports['cdn'])} (CDN/biên dùng chung): đây là cổng của CDN, "
                       "chưa chứng minh là cổng của máy chủ gốc (origin) hay của ứng dụng")
        return ports["pairs"], detail, not ports["complete"], ports
    if key == "nuclei":
        nuclei = results.summarize_nuclei(root)
        if not nuclei["found"]:
            return None
        detail = f"{nuclei['given_urls']}/{nuclei['live_urls']} URL đang sống được đưa cho nuclei"
        if nuclei["truncated"]:
            # V161_HOST_AUDIT.md C8: a scan can mix a quick (limit 50) and a full (limit 200) run; naming just one
            # limit claimed the wrong one applied to the truncated lượt. Say exactly which limit(s) were in play.
            if len(nuclei["limits"]) == 1:
                detail += f" (giới hạn {nuclei['limits'][0]} URL mỗi lượt — phần còn lại KHÔNG được quét)"
            elif nuclei["limits"]:
                detail += f" (mỗi lượt có giới hạn riêng: {', '.join(str(limit) for limit in nuclei['limits'])} URL — phần còn lại KHÔNG được quét)"
            else:
                detail += " (một số lượt bị cắt theo giới hạn URL mỗi lượt — phần còn lại KHÔNG được quét)"
        if nuclei["templates"] is not None:
            detail += f"; nuclei tự báo đã chạy {nuclei['templates']} template"
            if nuclei["requests"] is not None:
                detail += f", {nuclei['requests']} request"
            if nuclei["hosts"] is not None:
                detail += f" trên {nuclei['hosts']} host"
            detail += " (khác với số template ĐÃ CÀI trong Công cụ & môi trường)"
        elif nuclei.get("templates_unreliable") and nuclei["requests"] is not None:
            # V166_HOST_AUDIT.md P2: nuclei's own counter said "0 template" on the same line as real
            # requests/matches (seen with -as on v3.11.1). Say what IS trustworthy from that line; never repeat
            # the "0" as if it meant something.
            detail += f"; nuclei đã gửi {nuclei['requests']} request"
            if nuclei["hosts"] is not None:
                detail += f" trên {nuclei['hosts']} host"
            detail += " — số template nuclei tự báo không đáng tin ở lượt này (ghi 0 dù có request/kết quả thật)"
        if nuclei["timed_out"]:
            detail += " — DỞ DANG: nuclei bị cắt khi hết thời gian, số liệu trên chỉ tính tới lúc đó"
        if nuclei["failed"]:
            # V161_HOST_AUDIT.md C9: nuclei exiting on a real error (bad template, bad config…) used to look exactly
            # like "ran, found nothing". Say it failed; do not let the generic "0 kết quả" phrasing imply it ran clean.
            detail += " — LỖI: nuclei không chạy được (cấu hình hoặc template hỏng — xem nuclei/stats.jsonl); số liệu trên không đại diện cho một lượt quét thật"
        # "partial" (status "Chạy dở dang") is reserved for a run that was interrupted or failed; the 50/200 cap is a
        # designed limit, not an interruption, so a truncated-but-finished-cleanly run stays "ran".
        return nuclei["findings"], detail, nuclei["timed_out"] or nuclei["failed"], nuclei
    if key == "dir_fuzz":
        dirs = results.summarize_dirs(root)
        if not dirs["found"]:
            return None
        detail = f"{dirs['total']} phản hồi trên {len(dirs['hosts'])} host"
        if dirs["noise"]:
            detail += f"; {dirs['noise']} giống hệt nhau (trang chặn/trang mặc định chung) đã loại, còn {dirs['significant']} đáng xem"
        if dirs["blocked_only"]:
            detail += ". Chỉ có HTTP 403 ở: " + ", ".join(dirs["blocked_only"]) + " — 403 không chứng minh đường dẫn tồn tại"
        return dirs["significant"], detail, False, dirs
    if key == "takeover":
        path = Path(root) / "monitors" / "takeover" / "subjack.txt"
        if not path.is_file():
            return None
        info = summarize(path)
        detail = f"{info['candidates']} ứng viên (chưa xác minh), {info['not_vulnerable']} host đã kiểm và sạch"
        return info["candidates"], detail, False, info
    return None


def _matches(relative, pattern):
    return glob.fnmatch.fnmatch(relative, pattern)


def build_report(settings, database, scan_id, tools_missing=None):
    from backend.jobs.recon_orch import read_config
    with database.connect() as conn:
        scan = conn.execute("SELECT s.*,p.slug FROM scan_run s JOIN program p ON p.id=s.program_id WHERE s.id=?", (scan_id,)).fetchone()
        cfg_row = conn.execute("SELECT * FROM scan_config WHERE scan_run_id=?", (scan_id,)).fetchone()
    if scan is None:
        return None
    config = read_config(cfg_row) if cfg_row and cfg_row["depth"] else None
    stats = json.loads(scan["stats_json"] or "{}")
    missing = set(stats.get("missing_tools") if stats.get("missing_tools") is not None else (tools_missing or []))
    root = scan_root(settings, scan["slug"], scan_id)
    files = _safe_files(root)
    over = scan["status"] in {"done", "done_partial", "failed", "cancelled"}
    report = []
    for phase in PHASES:
        mine = []
        for path in files:
            rel = path.relative_to(root).as_posix()
            # step dirs are numbered ("0/urls/gau.txt"); monitors live at "monitors/<kind>/…"
            local = rel if rel.startswith("monitors/") else rel.split("/", 1)[1] if "/" in rel and rel.split("/", 1)[0].isdigit() else rel
            if any(_matches(local, pattern) for pattern in phase["files"]):
                mine.append({"path": rel, "name": path.name, "label": local, "bytes": path.stat().st_size, "lines": count_lines(path)})
        total = sum(f["lines"] or 0 for f in mine if f["label"] == phase["files"][0]) if mine else 0
        detail, partial, data = None, False, None
        got = structured_result(phase["key"], root) if mine else None
        if got:
            total, detail, partial, data = got
            total = len(total) if isinstance(total, list) else total
        reason = disabled_reason(config, phase["key"], historical_off=settings.BBASM_SKIP_HISTORICAL) if config else None
        tools_out = [t for t in phase["tools"] if t in missing]
        if reason and not any((f["lines"] or 0) for f in mine):
            status, label = "skipped", "Bỏ qua theo cấu hình"
        elif mine and partial:
            # Checked before the "any lines" branches below: a run cut short with zero results so far is still cut
            # short, not "ran — 0 kết quả" (nuclei timing out before its first match would otherwise say that).
            status, label, reason = "partial", "Chạy dở dang", "Công cụ dừng giữa chừng (hết thời gian hoặc bị ngắt): kết quả chỉ gồm phần đã xong, không đại diện cho mọi host."
        elif mine and any((f["lines"] or 0) for f in mine):
            status, label, reason = "ran", "Đã chạy", None
        elif mine:
            status, label, reason = "empty", "Chạy — 0 kết quả", "Có chạy nhưng không tìm thấy gì (không có nghĩa là an toàn)."
        elif phase["tools"] and (tools_out if phase.get("all_required") else len(tools_out) == len(phase["tools"])):
            status, label, reason = "missing_tool", "Thiếu công cụ", "Thiếu " + ", ".join(tools_out) + " nên bước này không được chạy."
        elif over:
            cut = any(st.get("status") in {"timeout", "skipped_budget"} for st in stats.get("stages") or [])
            status, label = ("timeout", "Hết thời gian") if cut else ("no_output", "Không có dữ liệu")
            reason = ("Một giai đoạn hết ngân sách thời gian trước khi tới bước này (xem bảng Giai đoạn)." if cut
                      else "Không có file kết quả (chưa tới bước này, bị huỷ, hoặc lỗi).")
        else:
            status, label = "pending", "Chưa tới"
        report.append({"key": phase["key"], "title": phase["title"], "what": phase["what"], "touches": phase["touches"],
                       "status": status, "status_label": label, "reason": reason, "count": total, "detail": detail, "partial": partial, "data": data,
                       "count_label": phase["count_label"], "files": mine, "view": phase["view"], "tools": phase["tools"]})
    return {"scan_id": scan_id, "slug": scan["slug"], "status": scan["status"], "depth": scan["depth"],
            "phases": report, "funnel": stats.get("url_funnel"), "missing_tools": sorted(missing),
            # How far the scan actually got: stages and their budgets, discovered/probed/unprobed, failed passive sources.
            "stages": stats.get("stages") or [], "coverage": stats.get("coverage"), "sources": stats.get("sources") or [],
            "path_rule_hosts": stats.get("path_rule_hosts") or {}, "partial_inputs": stats.get("partial_inputs") or [],
            "missing_needed": stats.get("missing_needed") or [], "tool_notes": stats.get("tool_notes") or [], "request_headers": stats.get("request_headers") or [],
            # what BBASM did with each asset type of the scope, and what an upgrade corrected on this scan after it ran
            "asset_coverage": stats.get("asset_coverage") or [], "manual_assets": stats.get("manual_assets") or [], "unprobed_hosts": (stats.get("unprobed_hosts") or [])[:500], "repairs": stats.get("repairs") or []}


# Credentials with a recognisable shape are hidden in every file, not only in scanner output.
_KNOWN_SECRETS = re.compile(
    r"AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|sk_(?:live|test)_[A-Za-z0-9]{10,}|AIza[0-9A-Za-z_\-]{30,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)")
_KEY_VALUE = re.compile(
    r"(?i)(\b[\w.-]*(?:token|secret|passw(?:or)?d|api[_-]?key|credential|authorization|bearer)[\w.-]*[\"']?\s*[=:]\s*[\"']?)((?:(?:bearer|basic)\s+)?[^\s\"',;&]{3,})")


def scrub(line):
    """Hide anything that looks like a credential. Plain URL lines keep their query values: they are recon data."""
    line = _KNOWN_SECRETS.sub(lambda m: m.group(0)[:4] + "…[ẩn]", line)
    if not line.lstrip().lower().startswith(("http://", "https://")):
        line = _KEY_VALUE.sub(lambda m: m.group(1) + "[ẩn]", line)
    return line


def redact(line, name):
    """Secret scanners store the secret itself; show the finding, not the credential."""
    if name in SECRET_FILES:
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                raise ValueError
            line = json.dumps({k: ("[ẩn]" if k in SECRET_KEYS else v) for k, v in data.items()}, ensure_ascii=False)
        except ValueError:
            line = re.sub(r"[A-Za-z0-9_\-+/=]{20,}", lambda m: m.group(0)[:4] + "…[ẩn]", line)
    return scrub(line)


def redacted_lines(path, name):
    """Stream a file with credentials hidden; the safe default for downloads."""
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            yield redact(line.rstrip("\n\r"), name) + "\n"


def read_artifact(settings, database, scan_id, relative, *, offset=0, limit=200, query="", reveal=False):
    """A page of a recon artifact. Path is validated against the scan's own directory."""
    with database.connect() as conn:
        scan = conn.execute("SELECT p.slug FROM scan_run s JOIN program p ON p.id=s.program_id WHERE s.id=?", (scan_id,)).fetchone()
    if scan is None:
        return None
    root = scan_root(settings, scan["slug"], scan_id)
    candidate = (root / relative)
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if (not resolved.is_relative_to(root) or candidate.is_symlink() or not resolved.is_file()
            or any(p.is_symlink() for p in candidate.parents if p != root and p.is_relative_to(root))
            or resolved.suffix.lower() not in TEXT_SUFFIXES or resolved.stat().st_size > MAX_SCAN_BYTES):
        return None
    needle = query.lower()
    page, matched, hidden = [], 0, False
    with resolved.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            line = line.rstrip("\n\r")
            # Search what the user can see: a hidden value must not be findable by guessing its characters.
            shown = line if reveal else redact(line, resolved.name)
            if needle and needle not in shown.lower():
                continue
            if offset <= matched < offset + limit:
                hidden = hidden or shown != line
                page.append(shown[:MAX_LINE] + ("…" if len(shown) > MAX_LINE else ""))
            matched += 1
    return {"path": relative, "name": resolved.name, "total": matched, "offset": offset, "limit": limit,
            "lines": page, "redacted": not reveal and (resolved.name in SECRET_FILES or hidden), "filtered": bool(needle)}
