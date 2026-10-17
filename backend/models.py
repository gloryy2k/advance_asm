"""API and scope types shared by resolve, review and later launch."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Depth = Literal["passive", "light", "strong"]
Category = Literal["web", "wildcard", "ip", "cidr", "source_code", "mobile", "other"]


class ScopeEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    pattern: str
    kind: Literal["in", "out"] = "in"
    asset_type: str
    category: Category
    instruction: str = ""


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: str = Field(min_length=1, max_length=2048)
    scope: list[str] = Field(default_factory=list, max_length=10000)
    scope_out: list[str] = Field(default_factory=list, max_length=10000)
    policy_text: str = Field(default="", max_length=100000)  # user-pasted policy/instructions
    name: str = Field(default="", max_length=100)  # optional human program name for raw scope (slug base)


# Hop-by-hop, framing and credential headers are never injected by the dashboard.
_FORBIDDEN_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "cookie", "authorization", "te", "upgrade",
                      "proxy-authorization", "proxy-connection", "keep-alive", "trailer", "expect"}


def validate_header(item: str) -> str:
    """"Name: value" for a header the program's policy asks for. Plain text only: no control characters, no secrets class."""
    if not isinstance(item, str) or ":" not in item:
        raise ValueError("Header phải có dạng 'Tên: giá trị'")
    name, _, value = item.partition(":")
    name, value = name.strip(), value.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,59}", name):
        raise ValueError(f"Tên header không hợp lệ: {name[:40]!r}")
    if name.lower() in _FORBIDDEN_HEADERS or name.lower().startswith(("proxy-", "sec-")):
        raise ValueError(f"Không cho phép header {name}: dùng cho khung giao thức hoặc thông tin xác thực")
    if not value or len(value) > 200 or not re.fullmatch(r"[\x20-\x7e]+", value):
        raise ValueError(f"Giá trị header {name} phải là 1–200 ký tự in được, không có xuống dòng")
    return f"{name}: {value}"


class ScanConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    depth: Depth
    threads: int = Field(ge=1, le=200)
    rate_limit: int = Field(ge=1, le=500)
    scan_timeout: int = Field(ge=1)
    nuclei_severity: str
    skip_nmap: bool
    skip_nuclei: bool
    skip_active_crawl: bool
    categories_enabled: list[Category]
    excluded_hosts: list[str] = Field(default_factory=list)
    # ── v1.2 user options (all optional: a config saved by an older client stays valid) ──
    skip_ffuf: bool = False            # strong only; ffuf never runs below strong
    # `*.example.com` grants subdomains only. The apex (`example.com`) is added to scope ONLY when the user lists it here AND confirms
    # (apex_confirmed) that the program's official policy allows it. Each entry must be the apex of an IN wildcard; OUT rules still win.
    include_apex: list[str] = Field(default_factory=list, max_length=20)
    apex_confirmed: bool = False
    # Budgets that depend on the size of the program. None = the server default (BBASM_NMAP_TIMEOUT, BBASM_FFUF_MAXTIME,
    # BBASM_NUCLEI_TIMEOUT, BBASM_DEEP_HOSTS). The whole-scan budget is scan_timeout; these bound single tools inside it.
    nmap_timeout: int | None = Field(default=None, ge=0, le=7200)       # seconds per nmap run, 0 = no cap
    ffuf_maxtime: int | None = Field(default=None, ge=0, le=7200)       # seconds per ffuf run, 0 = no cap
    nuclei_timeout: int | None = Field(default=None, ge=0, le=14400)     # seconds per nuclei run, 0 = no cap (every live URL is given to it, no per-run cap)
    deep_hosts: int | None = Field(default=None, ge=1, le=200)           # live discovered hosts that get the deep pass
    # Community nuclei templates tagged dos/fuzz/intrusive/brute-force are excluded unless the user opts in.
    nuclei_allow_intrusive: bool = False
    # nuclei -as: fingerprint each host (Wappalyzer-style) and run templates matching the detected technology, on
    # top of the severity/tag filters above. Which template fires depends on that host's own answer, decided by
    # nuclei at scan time -- never known in advance. When on, the shim also captures -vv (every template nuclei
    # loaded) to nuclei/templates_loaded.txt so Run can show what actually happened for that scan.
    nuclei_auto_select: bool = False
    skip_historical: bool = False      # no gau/wayback/crt.sh queries at all
    skip_takeover: bool = False
    skip_secrets: bool = False         # do not download/scan JS bundles
    max_js_files: int = Field(default=100, ge=0, le=100)
    url_exclude_patterns: list[str] = Field(default_factory=list, max_length=100)
    brief_budget_kb: int = Field(default=12, ge=4, le=12)
    brief_top_assets: int = Field(default=25, ge=5, le=50)
    brief_top_urls: int = Field(default=12, ge=0, le=30)
    # Headers a program's policy requires on every request that reaches the target ("X-HackerOne-Research: <user>").
    # Per program, not part of a profile: a profile is shared across programs, a header value is not.
    request_headers: list[str] = Field(default_factory=list, max_length=5)
    # Hosts that carry an OUT rule about a *path* get probe-only treatment (crawlers/templates cannot honour a path
    # exclusion). The user may knowingly allow the active tools on them; OUT URLs are still filtered from every result.
    allow_active_on_path_rules: bool = False
    # The user confirmed the policy allows directory brute-forcing (ffuf) for THIS scan; Strong refuses to run ffuf otherwise.
    ffuf_confirmed: bool = False
    # Repos (`repo:https://github.com/o/r`) whose scope text limits what may be tested (a sub-folder, "except …") and that the user
    # nevertheless confirms may be scanned as a whole for THIS scan. BBASM cannot enforce such a limit on a secrets scan, so
    # without this confirmation the repo is left for manual work.
    source_full_repo_ok: list[str] = Field(default_factory=list, max_length=50)
    # Ids of the user's own nuclei templates to run in addition to the official set, for THIS scan only.
    nuclei_custom: list[str] = Field(default_factory=list, max_length=50)
    # Header names from the policy that the user read and knowingly does not send ("X-HackerOne-Research"). Names, not
    # values; stored with the draft/schedule so every screen reads one answer. A header that is sent needs no entry.
    skipped_headers: list[str] = Field(default_factory=list, max_length=5)
    # Legacy blanket form of the same confirmation (accepted for older clients and stored schedules).
    skip_required_headers: bool = False

    def options(self) -> dict:
        return {name: getattr(self, name) for name in (*OPTION_FIELDS, "request_headers", "allow_active_on_path_rules", "skipped_headers", "skip_required_headers", "ffuf_confirmed", "nuclei_custom", "source_full_repo_ok", "include_apex", "apex_confirmed")}

    @field_validator("request_headers")
    @classmethod
    def safe_headers(cls, value):
        return [validate_header(item) for item in value]

    @field_validator("skipped_headers")
    @classmethod
    def safe_skipped(cls, value):
        names = []
        for name in value:
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,59}", name.strip()):
                raise ValueError(f"Tên header không hợp lệ: {str(name)[:40]!r}")
            if name.strip().lower() not in {n.lower() for n in names}:
                names.append(name.strip())
        return names

    @field_validator("include_apex")
    @classmethod
    def safe_apex(cls, value):
        out = []
        for item in value:
            host = str(item).strip().lower().rstrip(".")
            if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}", host):
                raise ValueError(f"Domain gốc không hợp lệ: {str(item)[:60]!r}")
            if host not in out:
                out.append(host)
        return out

    @field_validator("nuclei_custom")
    @classmethod
    def safe_custom_ids(cls, value):
        for item in value:
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", item):
                raise ValueError(f"Mã template không hợp lệ: {item[:40]!r}")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def drop_sent_from_skipped(self):
        # Once a header is actually sent, an old "I skip it" confirmation is meaningless and must not linger.
        sent = {h.split(":", 1)[0].strip().lower() for h in self.request_headers}
        self.skipped_headers = [n for n in self.skipped_headers if n.lower() not in sent]
        return self

    @field_validator("url_exclude_patterns")
    @classmethod
    def safe_patterns(cls, value):
        for pattern in value:
            if not pattern.startswith("/") or len(pattern) > 200 or not re.fullmatch(r"[A-Za-z0-9_\-./*?\[\]%~]+", pattern):
                raise ValueError(f"Mẫu đường dẫn không hợp lệ: {pattern[:40]!r} (bắt đầu bằng /, chỉ gồm chữ, số, - _ . / * ?)")
        return value

    @field_validator("nuclei_severity")
    @classmethod
    def valid_severity(cls, value):
        if value and any(part not in {"info", "low", "medium", "high", "critical"} for part in value.split(",")):
            raise ValueError("Unknown nuclei severity")
        return value


OPTION_FIELDS = ("skip_ffuf", "nmap_timeout", "ffuf_maxtime", "nuclei_timeout", "deep_hosts", "nuclei_allow_intrusive", "nuclei_auto_select", "skip_historical", "skip_takeover", "skip_secrets", "max_js_files",
                 "url_exclude_patterns", "brief_budget_kb", "brief_top_assets", "brief_top_urls")
# What a profile (a saved preset) may contain: how to scan, never *what* (scope stays per scan).
RECIPE_FIELDS = ("depth", "threads", "rate_limit", "scan_timeout", "nuclei_severity", "skip_nmap", "skip_nuclei",
                 "skip_active_crawl", *OPTION_FIELDS)


class LaunchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: ScanConfig | None = None
    # The user confirmed in Review that the program permits automated scanning. Recorded in the
    # scan and the audit trail; the UI requires it for any depth above passive.
    automation_ack: bool = False


class ResolveResponse(BaseModel):
    scan_id: int
    slug: str
    config: ScanConfig
    assets_by_category: dict[str, list[ScopeEntry]]
    warnings: list[str] = Field(default_factory=list)
