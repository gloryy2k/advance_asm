"""Fail-closed domain/IP scope decisions with a mandatory audit trail."""

import importlib.util
import ipaddress
import json
from pathlib import Path
import re
from threading import Lock
from urllib.parse import urlsplit

from backend.config import Settings
from backend.db import utc_now

_audit_lock = Lock()


def audit(path: Path, host: str, decision: str, rule: str, **extra) -> None:
    record = {"ts": utc_now(), "host": host, "decision": decision, "rule": rule, **extra}
    with _audit_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=True) + "\n")


def normalize_host(value: str) -> str:
    if not value or any(char.isspace() or ord(char) < 32 for char in value) or "\\" in value or "%" in value:
        raise ValueError("invalid host")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    parsed = urlsplit(value if "://" in value else "//" + value)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        raise ValueError("unsupported URL scheme")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("userinfo is not a scope host")
    _ = parsed.port  # Validate malformed/out-of-range ports.
    host = parsed.hostname
    if not host:
        raise ValueError("missing host")
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        host = host.rstrip(".").encode("idna").decode("ascii").lower()
        if len(host) > 253 or not all(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in host.split(".")
        ):
            raise ValueError("invalid domain")
        return host


def normalize_pattern(value: str) -> str:
    value = value.strip()
    if value.startswith("repo:"):
        resource = value[5:]
        parsed = urlsplit(resource)
        if (parsed.scheme != "https" or parsed.netloc.lower() != "github.com"
                or parsed.query or parsed.fragment
                or not re.fullmatch(r"/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?/?", parsed.path)
                or any(part in {".", ".."} for part in parsed.path.split("/"))):
            raise ValueError("invalid repository scope")
        return "repo:https://github.com" + parsed.path.rstrip("/").removesuffix(".git").lower()
    if value.startswith("*."):
        base = value[2:]
        if any(c in base for c in "/:*?#@"):
            raise ValueError("invalid wildcard")
        return "*." + normalize_host(base)
    if "/" in value and "://" not in value:
        return str(ipaddress.ip_network(value, strict=True))
    return normalize_host(value)


def _network(value):
    try:
        return ipaddress.ip_network(value, strict=True)
    except ValueError:
        return None


class ScopeGate:
    def __init__(self, allow: list[str], deny: list[str], audit_path: Path, settings: Settings):
        self.allow = [normalize_pattern(value) for value in allow]
        self.deny = [normalize_pattern(value) for value in deny]
        self.audit_path = Path(audit_path)
        path = settings.tool_path("scope_checker.py")
        spec = importlib.util.spec_from_file_location("bbasm_vendor_scope_checker", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Framework scope_checker.py unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # Real pinned interface is is_in_scope(), not in_scope() as §3 suggests.
        self.checker = module.ScopeChecker

    def _matches(self, target: str, pattern: str, *, deny: bool, resource: str) -> bool:
        if pattern.startswith("repo:"):
            parsed = urlsplit(resource.removeprefix("repo:"))
            if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
                return False
            path = parsed.path.rstrip("/").removesuffix(".git").lower()
            if any(part in {".", ".."} for part in path.split("/")):
                return False
            base = urlsplit(pattern[5:]).path
            return path == base or path.startswith(base + "/")
        candidate, rule = _network(target), _network(pattern)
        if candidate is not None or rule is not None:
            if candidate is None or rule is None or candidate.version != rule.version:
                return False
            # A CIDR may not sneak an excluded subnet/IP into an allowed scan range.
            return candidate.overlaps(rule) if deny else candidate.subnet_of(rule)
        return self.checker(domains=[pattern]).is_in_scope(target)

    def in_scope(self, target: str) -> bool:
        try:
            if any(char.isspace() or ord(char) < 32 for char in target):
                raise ValueError("invalid outbound target")
            host = normalize_pattern(target.removeprefix("repo:"))
            if host.startswith("*."):
                raise ValueError("wildcard is a rule, not an outbound target")
        except (ValueError, UnicodeError):
            audit(self.audit_path, str(target), "deny", "invalid_target")
            return False
        for pattern in self.deny:
            if self._matches(host, pattern, deny=True, resource=target):
                audit(self.audit_path, host, "deny", pattern)
                return False
        for pattern in self.allow:
            if self._matches(host, pattern, deny=False, resource=target):
                audit(self.audit_path, host, "allow", pattern)
                return True
        audit(self.audit_path, host, "deny", "no_matching_rule")
        return False
