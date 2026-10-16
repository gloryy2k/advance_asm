"""Validated environment settings; constructing settings performs no I/O writes."""

from pathlib import Path
import os
import re
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _is_windows_path(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", value)) or value.startswith("\\\\")


def quote_path(value: str) -> str:
    """Double-quote a path for the shell the user will paste it into.

    Windows paths (cmd/PowerShell) must keep their backslashes; POSIX paths need backslash,
    double quote, dollar and backtick escaped. json.dumps was wrong for both: it doubled every
    Windows backslash.
    """
    if _is_windows_path(value):
        return '"' + value.replace('"', "") + '"'
    return '"' + re.sub(r'(["\\$`])', r"\\\1", value) + '"'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8",
        extra="ignore", case_sensitive=True,
    )

    BBASM_BBROOT: Path = PROJECT_ROOT / "vendor" / "claude-bug-bounty"
    BBASM_TOOLS_SUBDIR: str = "tools"
    BBASM_DATA: Path = PROJECT_ROOT / "data"
    BBASM_TARGETS: Path = PROJECT_ROOT / "targets"
    BBASM_STATIC: Path = PROJECT_ROOT / "frontend" / "dist"
    BBASM_HOST_TARGETS: str | None = None  # verbatim: a WSL/POSIX path must not be rewritten by Windows Path semantics
    BBASM_SOURCE_TIMEOUT: int = Field(default=45, ge=5, le=600)       # per curl call to a passive source (crt.sh, Wayback)
    BBASM_SUBFINDER_TIMEOUT: int = Field(default=120, ge=30, le=1800)  # whole subfinder run
    BBASM_PROBE_BATCH: int = Field(default=50, ge=10, le=1000)        # discovered hosts probed per batch (a cut-off batch loses at most this many)
    BBASM_NMAP_TIMEOUT: int = Field(default=900, ge=0)                 # seconds per nmap run (0 = no cap); output so far is kept
    BBASM_NMAP_HOST_TIMEOUT: int = Field(default=120, ge=10)           # seconds per host, so one slow host cannot hold the run
    BBASM_FFUF_MAXTIME: int = Field(default=300, ge=0)                 # seconds per ffuf run (0 = no cap)
    BBASM_DEEP_HOSTS: int = Field(default=50, ge=1, le=500)            # live discovered hosts given the full Light/Strong pass
    BBASM_NUCLEI_TEMPLATES: Path | None = None   # managed templates dir; default <BBASM_DATA>/nuclei-templates (a volume in compose)
    BBASM_UPDATE_TEMPLATES: str = "auto"           # 0 never at boot; 1 every boot (background); auto only when none are installed yet
    BBASM_TEMPLATES_MIN: int = Field(default=100, ge=1)          # fewer templates than this after a download = incomplete, keep the old set
    BBASM_TEMPLATES_TIMEOUT: int = Field(default=900, ge=10, le=7200)
    BBASM_TEMPLATES_MIN_FREE_MB: int = Field(default=500, ge=1)
    BBASM_BIND: str = "127.0.0.1"
    BBASM_PORT: int = Field(default=8000, ge=1, le=65535)
    BB_THREADS: int = Field(default=50, ge=1, le=200)
    BB_RATE_LIMIT: int = Field(default=150, ge=1, le=500)
    BBASM_DEFAULT_DEPTH: Literal["passive", "light", "strong"] = "light"
    BBASM_MAX_CONCURRENT_SCANS: int = Field(default=2, ge=1)
    BBASM_RECON_DISABLED: bool = False
    BBASM_NO_INTERACTSH: bool = True
    BBASM_NO_REDIRECT: bool = True
    BBASM_SCOPE_CRAWL: bool = True
    BBASM_NO_VERIFY: bool = True
    BBASM_SKIP_HISTORICAL: bool = False
    BBASM_HISTORICAL_TIMEOUT: int = Field(default=60, ge=1, le=300)
    BBASM_SCAN_TIMEOUT_PASSIVE: int = Field(default=300, ge=1)
    BBASM_SCAN_TIMEOUT_LIGHT: int = Field(default=900, ge=1)
    BBASM_SCAN_TIMEOUT_STRONG: int = Field(default=2700, ge=1)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8000"
    SUBFINDER_CONFIG_DIR: Path | None = None
    CHAOS_KEY: SecretStr = SecretStr("")
    GITHUB_TOKEN: SecretStr = SecretStr("")
    H1_USER: SecretStr = SecretStr("")
    H1_TOKEN: SecretStr = SecretStr("")

    @field_validator("SUBFINDER_CONFIG_DIR", "BBASM_HOST_TARGETS", mode="before")
    @classmethod
    def empty_optional_path(cls, value):
        return None if value == "" else value

    @field_validator("BBASM_TOOLS_SUBDIR")
    @classmethod
    def relative_tools_directory(cls, value: str) -> str:
        # Validate both slash conventions even when running on Linux.
        parts = value.replace("\\", "/").split("/")
        if not value or value.startswith(("/", "\\")) or ":" in value or ".." in parts:
            raise ValueError("BBASM_TOOLS_SUBDIR must be a relative directory inside BBASM_BBROOT")
        return "/".join(parts)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def tools_dir(self) -> Path:
        return self.BBASM_BBROOT / self.BBASM_TOOLS_SUBDIR

    def hunt_target(self, slug: str) -> dict:
        """The `cd … && claude` command as the *user's* shell needs it, not the container's."""
        note = ""
        if self.BBASM_HOST_TARGETS is not None:
            base = str(self.BBASM_HOST_TARGETS)
            sep = "\\" if _is_windows_path(base) else "/"
            where = base.rstrip("/\\") + sep + slug
        elif str(self.BBASM_TARGETS).replace("\\", "/").startswith("/app/"):
            where = "targets/" + slug
            note = ("Chạy từ thư mục dự án BBASM trên máy bạn (thư mục ./targets được mount từ container). "
                    "Đặt BBASM_HOST_TARGETS trong .env để hiện đường dẫn tuyệt đối.")
        else:
            where = str((self.BBASM_TARGETS / slug).resolve())
        return {"hunt_command": f"cd {quote_path(where)} && claude", "hunt_note": note}

    @property
    def templates_dir(self) -> Path:
        return Path(self.BBASM_NUCLEI_TEMPLATES) if self.BBASM_NUCLEI_TEMPLATES else Path(self.BBASM_DATA) / "nuclei-templates"

    def tool_path(self, name: str) -> Path:
        if not name or name in {".", ".."} or any(c in name for c in "/\\:"):
            raise ValueError("tool name must be a filename")
        return self.tools_dir / name

    def tool_search_path(self) -> str:
        """Match the vendored recon PATH without changing the server environment."""
        home = Path(os.environ.get("HOME") or Path.home())
        extra = [str(home / "go" / "bin")]
        if os.name != "nt":
            extra.extend(["/opt/homebrew/bin", "/usr/local/bin"])
        return os.pathsep.join([*extra, os.environ.get("PATH", "")])

    def scan_timeout(self, depth: Literal["passive", "light", "strong"]) -> int:
        return {
            "passive": self.BBASM_SCAN_TIMEOUT_PASSIVE,
            "light": self.BBASM_SCAN_TIMEOUT_LIGHT,
            "strong": self.BBASM_SCAN_TIMEOUT_STRONG,
        }[depth]
