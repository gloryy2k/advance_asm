"""Nuclei templates as a managed data set: installed on purpose, updated atomically, never fetched in the middle of a scan.

Layout under `Settings.templates_dir` (a Docker named volume in compose, so it survives `up --force-recreate`):
  official/            live set (what nuclei is pointed at), with `.bbasm-templates.json` (count, time, source)
  official.staging/    the update downloads here first
  official.prev/       the set before the last successful update
  custom/<id>.yaml     templates the user imported (see `import_custom`)
  state.json           last update job (state, times, message) and the custom list
An update that fails or comes back incomplete leaves `official/` exactly as it was."""
import json
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

import yaml

from backend.jobs.scope_resolver import ScopeError
from backend.scope_gate import audit

MARKER = ".bbasm-templates.json"
SOURCE = "projectdiscovery/nuclei-templates"
MAX_CUSTOM_BYTES = 256 * 1024
MAX_CUSTOM_FILES = 200
FORBIDDEN_PROTOCOLS = {"code", "javascript", "headless", "file", "workflows", "flow"}
ALLOWED_PROTOCOLS = {"http", "dns", "ssl", "tcp", "whois"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_lock = threading.Lock()


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def count_yaml(directory, limit=None):
    total = 0
    for _ in Path(directory).rglob("*.yaml"):
        total += 1
        if limit and total >= limit:
            break
    return total


def official_ready(settings):
    """True when the managed official set has at least one template. Reads one small marker, not 14,000 files."""
    official = Path(settings.templates_dir) / "official"
    marker = official / MARKER
    try:
        if json.loads(marker.read_text(encoding="utf-8")).get("count", 0) > 0:
            return True
    except (OSError, ValueError):
        pass
    return official.is_dir() and next(official.rglob("*.yaml"), None) is not None


def custom_path(settings, template_id):
    if not ID_RE.fullmatch(template_id or ""):
        raise ScopeError("Mã template không hợp lệ", "invalid_template")
    return Path(settings.templates_dir) / "custom" / f"{template_id}.yaml"


def selected_custom(settings, ids):
    """Absolute paths of the chosen custom templates that exist; anything else is ignored (never guessed)."""
    paths = []
    for template_id in ids or []:
        try:
            path = custom_path(settings, template_id)
        except ScopeError:
            continue
        if path.is_file() and not path.is_symlink():
            paths.append(str(path))
    return paths


def snapshot_for_scan(settings, config):
    """What a scan will be run with, recorded in its stats so a result can be traced to the exact template set."""
    if config.depth == "passive" or config.skip_nuclei:
        return None
    base = Path(settings.templates_dir)
    try:
        marker = json.loads((base / "official" / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        marker = {}
    return {"official": {"count": marker.get("count"), "updated_at": marker.get("updated_at"), "version": marker.get("version"),
                         "managed": official_ready(settings)},
            "custom": [Path(p).stem for p in selected_custom(settings, getattr(config, "nuclei_custom", []))]}


class TemplateStore:
    def __init__(self, settings, run=subprocess.run):
        self.settings, self.run = settings, run
        self.base = Path(settings.templates_dir)
        self.state_file = self.base / "state.json"

    # ── state ──────────────────────────────────────────────
    def _state(self):
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data.setdefault("job", None)
        data.setdefault("custom", [])
        return data

    def _save(self, data):
        self.base.mkdir(parents=True, exist_ok=True)
        temp = self.state_file.with_suffix(".tmp")
        temp.write_text(json.dumps(data), encoding="utf-8")
        temp.replace(self.state_file)

    def _set_job(self, **fields):
        with _lock:
            data = self._state()
            data["job"] = {**(data["job"] or {}), **fields}
            self._save(data)
            return data["job"]

    def recover(self):
        """A job left 'running' by a stopped process cannot still be running."""
        job = self._state()["job"]
        if job and job.get("state") == "running":
            self._set_job(state="failed", finished_at=now(), message="Bị ngắt do máy chủ khởi động lại; bộ mẫu cũ vẫn được giữ nguyên.")

    def describe(self):
        data = self._state()
        official = self.base / "official"
        try:
            marker = json.loads((official / MARKER).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            marker = {}
        from backend.jobs.recon_orch import nuclei_templates_ready
        installed = nuclei_templates_ready(self.settings)
        return {"installed": installed, "count": marker.get("count") or 0, "updated_at": marker.get("updated_at"),
                "source": marker.get("source") or (SOURCE if installed else None), "version": marker.get("version"),
                "managed": official_ready(self.settings), "dir": str(self.base),
                "job": data["job"], "custom": data["custom"]}

    # ── official set ───────────────────────────────────────
    def start_update(self, background=True):
        """Begin one update. Refuses while another is running (also across restarts: a stale 'running' is recovered first)."""
        nuclei = shutil.which("nuclei", path=self.settings.tool_search_path())
        if not nuclei:
            raise ScopeError("Chưa cài nuclei nên chưa cập nhật được template.", "tool_missing")
        with _lock:
            data = self._state()
            if data["job"] and data["job"].get("state") == "running":
                raise ScopeError("Đang có một lần cập nhật template chạy.", "template_update_running")
            data["job"] = {"state": "running", "started_at": now(), "finished_at": None, "message": "Đang tải bộ template…", "count": None}
            self._save(data)
        audit(self.settings.BBASM_DATA / "audit.jsonl", "nuclei-templates", "allow", "template_update", source=SOURCE)
        if background:
            threading.Thread(target=self._update, args=(nuclei,), name="bbasm-templates", daemon=True).start()
        else:
            self._update(nuclei)
        return self._state()["job"]

    def _update(self, nuclei):
        staging, official, previous = self.base / "official.staging", self.base / "official", self.base / "official.prev"
        try:
            self.base.mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(self.base).free
            if free < self.settings.BBASM_TEMPLATES_MIN_FREE_MB * 1024 * 1024:
                raise RuntimeError(f"Không đủ dung lượng trống ({free // (1024 * 1024)} MB) để tải bộ template.")
            # nuclei installs into $HOME/nuclei-templates (verified default). A throw-away HOME keeps the update away from the
            # live set; only a complete result is moved into place.
            scratch = self.base / "update-home"
            shutil.rmtree(scratch, ignore_errors=True)
            shutil.rmtree(staging, ignore_errors=True)
            scratch.mkdir(parents=True)
            env = {k: v for k, v in os.environ.items() if k in {"LANG", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy",
                                                                   "https_proxy", "no_proxy", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"}}
            env["HOME"] = str(scratch)
            env["PATH"] = self.settings.tool_search_path()
            try:
                done = self.run([nuclei, "-update-templates"], env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=self.settings.BBASM_TEMPLATES_TIMEOUT)
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"Quá thời gian ({self.settings.BBASM_TEMPLATES_TIMEOUT} giây) khi tải bộ template.") from None
            output = re.sub(r"\x1b\[[0-9;]*m", "", (done.stdout or "") + (done.stderr or ""))[-4000:]
            fetched = scratch / "nuclei-templates"
            count = count_yaml(fetched) if fetched.is_dir() else 0
            # nuclei exits 0 even when the download failed (it only warns), so the result is judged by what arrived.
            if done.returncode or count < self.settings.BBASM_TEMPLATES_MIN:
                reason = self._explain(output)
                if not done.returncode:
                    reason += f" Bộ tải về chỉ có {count} template (cần ít nhất {self.settings.BBASM_TEMPLATES_MIN}); coi là tải không đầy đủ."
                raise RuntimeError(reason)
            fetched.rename(staging)
            shutil.rmtree(scratch, ignore_errors=True)
            version = self._version(staging)
            (staging / MARKER).write_text(json.dumps({"count": count, "updated_at": now(), "source": SOURCE, "version": version}), encoding="utf-8")
            shutil.rmtree(previous, ignore_errors=True)
            if official.exists():
                official.rename(previous)
            staging.rename(official)
            self._set_job(state="ok", finished_at=now(), count=count, message=f"Đã cài {count:,} template" + (f" (phiên bản {version})" if version else "") + ".")
        except Exception as exc:  # noqa: BLE001  the job reports every failure; the live set was never touched
            shutil.rmtree(staging, ignore_errors=True)
            self._set_job(state="failed", finished_at=now(), message=str(exc)[:500] + " Bộ template cũ (nếu có) vẫn được giữ.")

    @staticmethod
    def _explain(output):
        low = output.lower()
        warning = next((line for line in reversed(output.splitlines()) if "failed to update nuclei templates" in line.lower()), "")
        if "not enabled for this session" in low or "403" in low and "rate" not in low:
            return "GitHub từ chối truy cập (403): mạng/proxy chặn hoặc không có quyền tới kho template."
        if "rate limit" in low:
            return "GitHub từ chối vì vượt giới hạn truy cập (rate limit); thử lại sau."
        if "no such host" in low or "dial" in low or "timeout" in low or "connection" in low:
            return "Không kết nối được tới GitHub (mạng hoặc proxy)."
        if "no space" in low:
            return "Hết dung lượng đĩa khi tải."
        if warning:
            return "nuclei không tải được template: " + warning.split("cause=", 1)[-1][:200]
        return "nuclei báo lỗi khi cập nhật: " + (output.strip().splitlines()[-1][:200] if output.strip() else "không rõ nguyên nhân")

    @staticmethod
    def _version(directory):
        try:
            return json.loads((Path(directory) / ".templates-config.json").read_text(encoding="utf-8")).get("nuclei-templates-version")
        except (OSError, ValueError):
            return None

    # ── custom templates ───────────────────────────────────
    def import_custom(self, content: bytes):
        """Validate then store one uploaded YAML. The template is never run here and never joins a scan unless selected."""
        if len(content) > MAX_CUSTOM_BYTES:
            raise ScopeError(f"Template quá lớn (tối đa {MAX_CUSTOM_BYTES // 1024} KB).", "invalid_template")
        try:
            text = content.decode("utf-8")
            data = yaml.safe_load(text)
        except (UnicodeDecodeError, yaml.YAMLError):
            raise ScopeError("Không đọc được YAML (cần UTF-8 hợp lệ).", "invalid_template") from None
        if not isinstance(data, dict):
            raise ScopeError("Template phải là một đối tượng YAML.", "invalid_template")
        template_id = str(data.get("id", ""))
        if not ID_RE.fullmatch(template_id):
            raise ScopeError("`id` phải gồm chữ thường, số, - hoặc _ (tối đa 64 ký tự).", "invalid_template")
        problem = self._unsafe(data)
        if problem:
            raise ScopeError(problem, "invalid_template")
        with _lock:
            state = self._state()
            if any(item["id"] == template_id for item in state["custom"]):
                raise ScopeError(f"Đã có template riêng với id `{template_id}`.", "template_duplicate")
            if len(state["custom"]) >= MAX_CUSTOM_FILES:
                raise ScopeError("Đã đủ số template riêng tối đa.", "invalid_template")
            path = custom_path(self.settings, template_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            error = self._validate_with_nuclei(path)
            if error:
                path.unlink(missing_ok=True)
                raise ScopeError(error, "invalid_template")
            info = (data.get("info") or {}) if isinstance(data.get("info"), dict) else {}
            entry = {"id": template_id, "name": str(info.get("name") or template_id)[:120], "bytes": len(content), "added_at": now(),
                     "severity": str(info.get("severity") or "info")[:12],
                     "protocols": sorted(k for k in data if k in ALLOWED_PROTOCOLS)}
            state["custom"].append(entry)
            self._save(state)
        audit(self.settings.BBASM_DATA / "audit.jsonl", "nuclei-templates", "allow", "custom_template_imported", template=template_id)
        return entry

    @staticmethod
    def _unsafe(data):
        bad = [k for k in data if k in FORBIDDEN_PROTOCOLS]
        if bad:
            return f"Không nhận template dùng `{bad[0]}` (có thể chạy mã hoặc đọc tệp)."
        protocols = [k for k in data if k in ALLOWED_PROTOCOLS]
        if not protocols:
            return "Template phải có ít nhất một giao thức: " + ", ".join(sorted(ALLOWED_PROTOCOLS)) + "."
        # A request line or path that begins with a literal scheme is a request to someone else, not to the scan target.
        absolute = re.compile(r"(?im)^\s*(?:[A-Z]+\s+)?(?:https?|ftp|gopher)://")

        def walk(value):
            if isinstance(value, str):
                return bool(absolute.search(value))
            if isinstance(value, dict):
                return any(walk(v) for v in value.values())
            if isinstance(value, list):
                return any(walk(v) for v in value)
            return False
        for key in protocols:
            if walk(data[key]):
                return "Template chứa URL cố định (không phải {{BaseURL}}); không nhận vì sẽ gửi request tới nơi khác target."
        for block in data.get("tcp") or []:
            hosts = block.get("host") if isinstance(block, dict) else None
            if hosts and any("{{" not in str(h) for h in (hosts if isinstance(hosts, list) else [hosts])):
                return "Khối tcp phải nhắm vào {{Hostname}}/{{Host}} của target, không phải địa chỉ cố định."
        return ""

    def _validate_with_nuclei(self, path):
        nuclei = shutil.which("nuclei", path=self.settings.tool_search_path())
        if not nuclei:
            return ""   # static checks above still ran; validation by nuclei needs the binary
        home = self.base / "home"
        home.mkdir(parents=True, exist_ok=True)
        try:
            done = self.run([nuclei, "-validate", "-duc", "-t", str(path)], env={"PATH": self.settings.tool_search_path(), "HOME": str(home)},
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return "nuclei không kiểm tra được template (hết thời gian)."
        if done.returncode:
            text = (done.stdout + done.stderr).strip().splitlines()
            return "nuclei -validate từ chối template: " + (text[-1][:200] if text else "không rõ lý do")
        return ""

    def delete_custom(self, template_id):
        path = custom_path(self.settings, template_id)
        with _lock:
            state = self._state()
            if not any(item["id"] == template_id for item in state["custom"]):
                raise ScopeError("Không có template riêng này.", "template_not_found")
            path.unlink(missing_ok=True)
            state["custom"] = [item for item in state["custom"] if item["id"] != template_id]
            self._save(state)
        audit(self.settings.BBASM_DATA / "audit.jsonl", "nuclei-templates", "allow", "custom_template_deleted", template=template_id)
