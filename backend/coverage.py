"""What BBASM will (and will not) do for each asset of a scope, said plainly. One source for Review, Run and Program, so a
Strong scan never reads as "everything was scanned".

mode: recon (full pipeline for the depth) | recon_host (a URL with a path: recon runs on the HOST) | secrets_only (repo secret scan)
      | manual_confirm (needs the user's explicit confirmation before anything automatic) | manual (stored for hand work)
      | passive_only (only public sources at this depth) | off (the user switched the group off)"""
from urllib.parse import urlsplit

AUTOMATIC_CATEGORIES = {"wildcard", "web", "ip", "cidr", "source_code"}


def _is_github_repo(pattern):
    url = pattern.removeprefix("repo:")
    return urlsplit(url).netloc == "github.com" and len(urlsplit(url).path.strip("/").split("/")) >= 2


def repo_is_restricted(entry):
    """The scope text says something about this repo. We cannot parse "only code/crates except test" into an enforceable rule,
    so any instruction counts as a possible limit."""
    return bool((entry.get("instruction") or "").strip())


def entry_coverage(entry, config):
    """entry: dict with pattern, category, instruction. config: the ScanConfig that would run."""
    pattern, category = entry["pattern"], entry["category"]
    instruction = (entry.get("instruction") or "").strip()
    out = {"pattern": pattern, "category": category, "instruction": instruction[:600], "needs_confirmation": False}
    if category in {"mobile", "other"}:
        return {**out, "mode": "manual", "label": "Chỉ lưu để làm tay",
                "detail": "BBASM không tải app, không gửi request tới loại asset này. Chỉ ghi vào PROGRAM.md và brief; quyền kiểm thử do bạn quyết định theo policy."}
    if category not in config.categories_enabled:
        return {**out, "mode": "off", "label": "Đã tắt cho lần quét này", "detail": "Nhóm asset này bị bỏ chọn ở Review."}
    if category == "source_code":
        if config.depth == "passive":
            return {**out, "mode": "manual", "label": "Làm tay (Passive không tải repo)", "detail": "Mức Passive không clone hay tải repo."}
        if not _is_github_repo(pattern):
            return {**out, "mode": "manual", "label": "Làm tay (không phải GitHub)", "detail": "Chỉ repo GitHub mới có bước quét bí mật tự động; repo khác chỉ được ghi nhận."}
        if repo_is_restricted(entry) and pattern not in config.source_full_repo_ok:
            return {**out, "mode": "manual_confirm", "needs_confirmation": True, "label": "Khóa tự động: scope có giới hạn",
                    "detail": "Hướng dẫn của program có thể chỉ cho phép một phần repo. Quét bí mật đọc TOÀN BỘ repo và lịch sử git; BBASM chưa giới hạn được theo thư mục "
                              "nên không tự chạy. Đọc hướng dẫn, làm tay phần được phép, hoặc xác nhận cho phép quét cả repo."}
        return {**out, "mode": "secrets_only", "label": "Chỉ quét bí mật trong repo",
                "detail": "trufflehog/noseyparker/gitleaks trên repo (toàn bộ lịch sử). Không có SAST, dependency scan hay đọc code." +
                          (" Bạn đã xác nhận quét cả repo dù scope có giới hạn." if repo_is_restricted(entry) else "")}
    if config.depth == "passive":
        return {**out, "mode": "passive_only", "label": "Chỉ nguồn công khai",
                "detail": "Passive không gửi request tới target: subdomain và URL lịch sử từ nguồn công khai."}
    if category == "wildcard":
        return {**out, "mode": "recon", "label": "Recon đầy đủ theo mức quét",
                "detail": "Liệt kê subdomain, probe HTTP, rồi quét sâu một số host đang sống. Chỉ subdomain; domain gốc không được cấp quyền."}
    if category == "web" and "://" in pattern and urlsplit(pattern).path not in {"", "/"}:
        path = urlsplit(pattern).path
        return {**out, "mode": "recon_host", "label": "Recon trên cả host (path không giới hạn request)",
                "detail": f"Scope ghi đường dẫn {path}, nhưng công cụ chạy theo HOST {urlsplit(pattern).hostname}: crawl/nuclei/ffuf có thể gửi request tới đường dẫn khác. "
                          "BBASM chỉ lọc kết quả ngoài đường dẫn, không giới hạn request."}
    return {**out, "mode": "recon", "label": "Recon đầy đủ theo mức quét",
            "detail": "Probe HTTP, crawl, nuclei; Strong thêm nmap/ffuf tùy cấu hình và xác nhận."}


def scope_coverage(entries, config):
    items = [e if isinstance(e, dict) else e.model_dump() for e in entries]
    return [entry_coverage(e, config) for e in items if e["kind"] == "in"]


def coverage_summary(rows):
    counts = {}
    for row in rows:
        counts[row["mode"]] = counts.get(row["mode"], 0) + 1
    return counts
