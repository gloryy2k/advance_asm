"""One description of every tool and data set BBASM relies on, and one way to read how each stands on this machine.

The health endpoint, the Review/Run warnings and the Tools page all read this table, so they cannot disagree.
Reading never runs a tool (no network, no target); only `probe_versions` does, and only when the user asks."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from backend.asm.phases import PHASES

DEPTHS = ("passive", "light", "strong")
# id: (kind, short name, what it is for, remedy). kind: binary | data | framework.
# `required` lists the depths where a missing one weakens the scan; nothing listed = optional.
TOOLS = {
    "subfinder": ("binary", "subfinder", "Tìm subdomain từ nguồn công khai.", ("passive", "light", "strong")),
    "gau": ("binary", "gau", "Lấy URL lịch sử từ archive.", ("passive", "light", "strong")),
    "httpx": ("binary", "httpx (ProjectDiscovery)", "Probe HTTP: trạng thái, tiêu đề, công nghệ.", ("light", "strong")),
    "katana": ("binary", "katana", "Crawl chủ động host đang chạy.", ("light", "strong")),
    "nuclei": ("binary", "nuclei", "Quét mẫu lỗi đã biết.", ("light", "strong")),
    "nuclei-templates": ("data", "nuclei-templates", "Bộ mẫu kiểm tra cho nuclei (không có thì nuclei không chạy).", ("light", "strong")),
    "nmap": ("binary", "nmap", "Quét cổng và dịch vụ (Strong).", ("strong",)),
    "ffuf": ("binary", "ffuf", "Dò thư mục bằng danh sách đường dẫn (Strong).", ("strong",)),
    "amass": ("binary", "amass", "Tìm subdomain bổ sung (Strong).", ("strong",)),
    "trufflehog": ("binary", "trufflehog", "Quét khoá/token rò rỉ trong file JS.", ()),
    "noseyparker": ("binary", "noseyparker", "Quét bí mật thay thế trufflehog.", ()),
    "subjack": ("binary", "subjack", "Tìm subdomain có thể bị chiếm (takeover).", ()),
    "dnsreaper": ("binary", "dnsreaper", "Tìm takeover thay thế subjack.", ()),
    "git": ("binary", "git", "Dùng khi tải kho mã nguồn.", ()),
    "bbscope": ("binary", "bbscope", "Công cụ ngoài để gom scope; không scan nào phụ thuộc.", ()),
    "curl": ("binary", "curl", "Tải file JS, kiểm file cấu hình, nguồn URL lịch sử.", ()),
    "bash": ("binary", "bash", "Chạy engine recon.", ()),
}
FRAMEWORK = {
    "recon_engine.sh": "Engine recon", "scope_aggregator.sh": "Gom scope", "scope_checker.py": "Kiểm scope",
    "recon_adapter.py": "Adapter recon", "intel_engine.py": "Tra cứu intel", "takeover_scanner.sh": "Quét takeover",
    "secrets_hunter.sh": "Quét bí mật",
}
EXECUTABLES = ("bash", "subfinder", "httpx", "nuclei", "katana", "gau", "amass", "ffuf", "nmap", "git", "bbscope", "trufflehog")   # as reported by /api/health
DEPTH_TOOLS = {depth: [t for t, spec in TOOLS.items() if depth in spec[3]] for depth in DEPTHS}
OPTIONAL_TOOLS = tuple(t for t in ("bbscope", "git", "trufflehog") if t in TOOLS)
VERSION_FLAGS = {"subfinder": ["-version", "-duc"], "httpx": ["-version", "-duc"], "katana": ["-version", "-duc"],
                 "nuclei": ["-version", "-duc"], "ffuf": ["-V"], "amass": ["-version"], "gau": ["--version"], "nmap": ["--version"],
                 "git": ["--version"], "trufflehog": ["--version"], "curl": ["--version"], "bash": ["--version"]}
REMEDY_BINARY = ("Có sẵn trong image Docker của BBASM; nếu thiếu thì build lại image (`docker compose build`). "
                 "Chạy ngoài Docker: cài công cụ rồi đưa vào PATH hoặc ~/go/bin.")
REMEDY = {"nuclei-templates": "Bộ mẫu chưa có. Cài bằng nút cập nhật templates ở trang này.",
          "httpx": "Cần httpx của ProjectDiscovery (bản Python `httpx` cùng tên không dùng được).",
          "bash": "Cần bash (Linux/WSL2/Docker)."}


def _pinned(root):
    path = Path(root) / "scripts" / "tool-releases.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))["tools"]
        return {name: info.get("version") for name, info in data.items()}
    except (OSError, ValueError, KeyError):
        return {}


def phases_using(tool):
    return [{"key": p["key"], "title": p["title"]} for p in PHASES if tool in p["tools"]]


def _binary_state(settings, tool):
    from backend.api import health as h
    found = shutil.which(tool, path=settings.tool_search_path())
    if found is None:
        return "missing_binary", "Không thấy trên máy chủ."
    if tool == "httpx" and not h.is_projectdiscovery_httpx(found):
        return "wrong_binary", f"{found} là httpx Python, không phải bản ProjectDiscovery."
    return "ready", found


def read_check_cache(settings):
    try:
        return json.loads((settings.BBASM_DATA / "tools_check.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def tool_inventory(settings, templates=None):
    """Every tool as a dict: state, why, which depths need it, which steps use it, versions. Never executes anything.

    `templates`: description of the Nuclei template set (installed count, source, time), supplied by the template store."""
    from backend.jobs.recon_orch import nuclei_templates_ready
    pinned, checked = _pinned(Path(__file__).resolve().parent.parent), read_check_cache(settings)
    rows = []
    for tool, (kind, label, purpose, required) in TOOLS.items():
        if kind == "binary":
            state, detail = _binary_state(settings, tool)
        else:
            nuclei_state, _ = _binary_state(settings, "nuclei")
            if nuclei_state != "ready":
                state, detail = "missing_data", "Cần nuclei trước."
            elif nuclei_templates_ready(settings):
                state, detail = "ready", "Đã có bộ mẫu."
            else:
                state, detail = "missing_data", "Chưa có file template nào."
        used = phases_using(tool)
        rows.append({"id": tool, "kind": kind, "label": label, "purpose": purpose, "state": state, "detail": detail,
                     "required_for": list(required), "optional": not required, "used_by": used,
                     "pinned_version": pinned.get(tool), "version": (checked.get(tool) or {}).get("version"),
                     "checked_at": (checked.get(tool) or {}).get("checked_at"),
                     "remedy": "" if state == "ready" else REMEDY.get(tool) or (REMEDY_BINARY if kind == "binary" else ""),
                     **({"templates": templates} if tool == "nuclei-templates" and templates else {})})
    for name, label in FRAMEWORK.items():
        ok = settings.tool_path(name).is_file()
        rows.append({"id": name, "kind": "framework", "label": label, "purpose": f"Tệp của bộ khung recon ({name}).",
                     "state": "ready" if ok else "missing_data", "detail": "" if ok else "Không thấy trong thư mục tools của framework.",
                     "required_for": [], "optional": False, "used_by": [], "pinned_version": None, "version": None, "checked_at": None,
                     "remedy": "" if ok else "Bộ khung (vendor/claude-bug-bounty) bị thiếu hoặc cấu hình BBASM_BBROOT sai."})
    for row in rows:
        row["impact"] = impact(row)
    return rows


def impact(row):
    """What a missing tool costs at each depth, in words the Review page can repeat."""
    out = {}
    for depth in DEPTHS:
        if row["state"] == "ready":
            out[depth] = "ok" if depth in row["required_for"] or row["used_by"] else "unused"
        elif depth in row["required_for"]:
            steps = ", ".join(u["title"] for u in row["used_by"]) or row["label"]
            out[depth] = f"Bước bị bỏ qua: {steps}"
        else:
            out[depth] = "optional" if row["optional"] else "unused"
    return out


def probe_versions(settings, only=None, timeout=8):
    """Run `<tool> -version` (update checks off) for tools that are present. Explicit user action only."""
    from datetime import datetime, timezone
    found = {}
    env = {"PATH": settings.tool_search_path(), "HOME": os.environ.get("HOME", "/tmp"), "LANG": "C"}
    for tool, flags in VERSION_FLAGS.items():
        if only and tool not in only:
            continue
        binary = shutil.which(tool, path=settings.tool_search_path())
        if not binary:
            continue
        try:
            done = subprocess.run([binary, *flags], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
            match = re.search(r"v?\d+\.\d+(?:\.\d+)*", (done.stdout + done.stderr)[:4000])
            found[tool] = {"version": match.group(0) if match else None, "ok": done.returncode == 0,
                           "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
        except (OSError, subprocess.TimeoutExpired):
            found[tool] = {"version": None, "ok": False, "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    cache = {**read_check_cache(settings), **found}
    settings.BBASM_DATA.mkdir(parents=True, exist_ok=True)
    (settings.BBASM_DATA / "tools_check.json").write_text(json.dumps(cache), encoding="utf-8")
    return found
