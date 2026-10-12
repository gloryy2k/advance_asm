"""API and scope types shared by resolve, review and later launch."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class ScanConfig(BaseModel):
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


class ResolveResponse(BaseModel):
    scan_id: int
    slug: str
    config: ScanConfig
    assets_by_category: dict[str, list[ScopeEntry]]
    warnings: list[str] = Field(default_factory=list)
