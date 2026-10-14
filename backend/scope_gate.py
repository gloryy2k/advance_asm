"""Fail-closed domain/IP scope decisions with a mandatory audit trail."""

import fnmatch
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


# Hosts whose repositories we can name precisely, with the deepest path allowed (GitLab has subgroups).
REPO_HOSTS = {"github.com": 2, "gitlab.com": 6, "bitbucket.org": 2}


def normalize_repo(resource: str) -> str:
    """https://host/org[/repo] -> canonical form. A trailing /* means "the organisation" and nothing wider."""
    parsed = urlsplit(resource)
    host = parsed.netloc.lower()
    if parsed.scheme != "https" or host not in REPO_HOSTS or parsed.query or parsed.fragment:
        raise ValueError("invalid repository scope")
    path = parsed.path
    if path.endswith("/*"):
        path = path[:-2]
    segments = path.rstrip("/").removesuffix(".git").strip("/").split("/")
    if not 1 <= len(segments) <= REPO_HOSTS[host] or any(
            not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in {".", ".."} for part in segments):
        raise ValueError("invalid repository scope")
    return f"https://{host}/" + "/".join(segments).lower()


def normalize_pattern(value: str, *, deny: bool = False) -> str:
    """Canonical scope rule. With deny=True a "*" inside a label is allowed (it can only exclude more, never widen)."""
    value = value.strip()
    if value.startswith("repo:"):
        return "repo:" + normalize_repo(value[5:])
    if value.startswith("*."):
        base = value[2:]
        if any(c in base for c in "/:*?#@"):
            raise ValueError("invalid wildcard")
        return "*." + normalize_host(base)
    if deny and "*" in value:
        value = value.lower()
        if not re.fullmatch(r"[a-z0-9*-]+(?:\.[a-z0-9*-]+)+", value) or value.startswith(".") or ".." in value:
            raise ValueError("invalid glob")
        return value
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
        self.deny = [normalize_pattern(value, deny=True) for value in deny]
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
            base = urlsplit(pattern[5:])
            if parsed.scheme != "https" or parsed.netloc.lower() != base.netloc or parsed.netloc.lower() not in REPO_HOSTS:
                return False
            path = parsed.path.rstrip("/").removesuffix(".git").lower()
            if any(part in {".", ".."} for part in path.split("/")):
                return False
            return path == base.path or path.startswith(base.path + "/")
        if deny and "*" in pattern and not pattern.startswith("*."):
            return fnmatch.fnmatchcase(target, pattern)   # conservative: "*" also spans dots
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
