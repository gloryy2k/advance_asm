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
    {"key": "live_probe", "title": "Probe HTTP", "touches": True, "tools": ["httpx", "dnsx"],
     "what": "Hỏi từng host xem có phản hồi web không: mã trạng thái, tiêu đề, công nghệ (tech).",
     "files": ["live/httpx_full.txt", "live/urls.txt"], "count_label": "host phản hồi", "view": {"kind": "hosts", "label": "Xem host + trạng thái"}},
    {"key": "port_scan", "title": "Quét cổng", "touches": True, "tools": ["nmap"],
     "what": "nmap tìm cổng mở và dịch vụ. Chỉ chạy ở mức Strong.",
     "files": ["ports/nmap_greppable.txt", "ports/nmap_results.txt"], "count_label": "dòng", "view": {"kind": "file", "label": "Đọc kết quả nmap"}},
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
     "files": ["dirs/*.json"], "count_label": "đường dẫn", "view": {"kind": "file", "label": "Đọc kết quả ffuf"}},
    {"key": "config_expose", "title": "File cấu hình lộ", "touches": True, "tools": ["curl"],
     "what": "Kiểm tra vài file hay bị lộ (.env, config.js…) trên host đang chạy.",
     "files": ["exposure/config_files.txt"], "count_label": "file lộ", "view": {"kind": "file", "label": "Đọc danh sách"}},
    {"key": "param_discover", "title": "Tham số", "touches": False, "tools": [],
     "what": "Thống kê tham số query từ URL đã thu thập, đánh dấu tên hay gặp lỗi (id, redirect, file…).",
     "files": ["params/unique_params.txt", "params/interesting_params.txt"], "count_label": "tham số", "view": {"kind": "urls", "label": "Xem URL có tham số", "filter": {"tag": "params"}}},
    {"key": "nuclei", "title": "Nuclei", "touches": True, "tools": ["nuclei"],
     "what": "Chạy bộ mẫu kiểm tra lỗi đã biết theo mức nghiêm trọng bạn chọn.",
     "files": ["nuclei/findings.jsonl"], "count_label": "finding", "view": {"kind": "findings", "label": "Xem findings", "filter": {"type": "nuclei"}}},
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


def plan_for(config, settings, missing_tools):
    """What a scan with this config WILL do, step by step — shown in Review before anything runs."""
    missing = set(missing_tools)
    out = []
    for phase in PHASES:
        reason = disabled_reason(config, phase["key"], historical_off=settings.BBASM_SKIP_HISTORICAL)
        absent = [t for t in phase["tools"] if t in missing]
        if reason:
            status = "off"
        elif phase["tools"] and len(absent) == len(phase["tools"]):
            status, reason = "missing_tool", "Thiếu " + ", ".join(absent) + " — bước này sẽ bị bỏ qua."
        else:
            status = "on"
        out.append({"key": phase["key"], "title": phase["title"], "what": phase["what"], "touches": phase["touches"],
                    "status": status, "reason": reason, "view": phase["view"]})
    return out


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
        if path.stat().st_size > MAX_SCAN_BYTES:
            return None
        total, last = 0, b""
        with path.open("rb") as stream:
            while chunk := stream.read(1 << 20):
                total += chunk.count(b"\n")
                last = chunk[-1:]
        return total + (1 if last and last != b"\n" else 0)
    except OSError:
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
        reason = disabled_reason(config, phase["key"], historical_off=settings.BBASM_SKIP_HISTORICAL) if config else None
        tools_out = [t for t in phase["tools"] if t in missing]
        if reason and not any((f["lines"] or 0) for f in mine):
            status, label = "skipped", "Bỏ qua"
        elif mine and any((f["lines"] or 0) for f in mine):
            status, label = "ran", "Đã chạy"
        elif mine:
            status, label, reason = "empty", "Chạy — 0 kết quả", "Có chạy nhưng không tìm thấy gì (không có nghĩa là an toàn)."
        elif phase["tools"] and len(tools_out) == len(phase["tools"]):
            status, label, reason = "missing_tool", "Thiếu công cụ", "Thiếu " + ", ".join(tools_out) + " nên bước này không chạy."
        elif over:
            status, label, reason = "no_output", "Không có dữ liệu", "Không có file kết quả (chưa tới bước này, bị huỷ, hoặc lỗi)."
        else:
            status, label = "pending", "Chưa tới"
        report.append({"key": phase["key"], "title": phase["title"], "what": phase["what"], "touches": phase["touches"],
                       "status": status, "status_label": label, "reason": reason, "count": total,
                       "count_label": phase["count_label"], "files": mine, "view": phase["view"], "tools": phase["tools"]})
    return {"scan_id": scan_id, "slug": scan["slug"], "status": scan["status"], "depth": scan["depth"],
            "phases": report, "funnel": stats.get("url_funnel"), "missing_tools": sorted(missing)}


def redact(line, name):
    """Secret scanners store the secret itself; show the finding, not the credential."""
    if name not in SECRET_FILES:
        return line
    try:
        data = json.loads(line)
        if isinstance(data, dict):
            return json.dumps({k: ("[ẩn]" if k in SECRET_KEYS else v) for k, v in data.items()}, ensure_ascii=False)
    except ValueError:
        pass
    return re.sub(r"[A-Za-z0-9_\-+/=]{20,}", lambda m: m.group(0)[:4] + "…[ẩn]", line)


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
    page, matched = [], 0
    with resolved.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            line = line.rstrip("\n\r")
            if needle and needle not in line.lower():
                continue
            if offset <= matched < offset + limit:
                text = line if reveal else redact(line, resolved.name)
                page.append(text[:MAX_LINE] + ("…" if len(text) > MAX_LINE else ""))
            matched += 1
    return {"path": relative, "name": resolved.name, "total": matched, "offset": offset, "limit": limit,
            "lines": page, "redacted": resolved.name in SECRET_FILES and not reveal, "filtered": bool(needle)}
