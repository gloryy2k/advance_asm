"""API and scope types shared by resolve, review and later launch."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    def options(self) -> dict:
        return {name: getattr(self, name) for name in (*OPTION_FIELDS, "request_headers")}

    @field_validator("request_headers")
    @classmethod
    def safe_headers(cls, value):
        return [validate_header(item) for item in value]

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


OPTION_FIELDS = ("skip_ffuf", "skip_historical", "skip_takeover", "skip_secrets", "max_js_files",
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
