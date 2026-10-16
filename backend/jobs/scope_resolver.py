"""Two-phase scope resolution: classification and draft persistence only."""

from collections import defaultdict
import hashlib
import ipaddress
import json
import re
from urllib.parse import urlsplit

from backend.config import Settings
from backend.db import Database, utc_now
from backend.trust import launch_gate
from backend.models import ResolveRequest, ResolveResponse, ScanConfig, ScopeEntry
from backend.scope_gate import audit, normalize_host, normalize_pattern, normalize_repo


class ScopeError(ValueError):
    def __init__(self, message: str, code: str = "invalid_scope"):
        super().__init__(message)
        self.code = code


_H1_SUFFIXES = {"policy", "policy_scopes", "thanks", "hacktivity", "reports", "scope"}
_H1_RESERVED = {"reports", "users", "directory", "hacktivity", "leaderboard", "settings", "sign_in",
                "bugs", "opportunities", "teams", "organizations", "security", "about", "raw",
                "bug-bounty-programs", "hackers", "customers", "resources", "contact", "login"}
_H1_BAD = "Nhập h1:<handle>, URL chương trình hackerone.com/<handle> hoặc handle trần"


def h1_handle(value: str) -> str:
    """Normalise any reasonable way of naming a HackerOne program to its handle.

    The value is only used to look up metadata, never fetched, so query strings,
    fragments, `www.`, a missing scheme and known page suffixes are safe to drop.
    Foreign hosts, userinfo and unknown path shapes are still rejected.
    """
    value = value.strip().strip("\"'`<>").strip()
    if value.lower().startswith("h1:"):
        handle = value[3:].strip()
    elif "/" not in value and "." not in value and ":" not in value and value.lower() != "raw":
        handle = value.lstrip("@")
    else:
        if "://" not in value:
            value = "https://" + value
        try:
            url = urlsplit(value)
            if url.scheme not in {"http", "https"} or url.netloc.lower() not in {"hackerone.com", "www.hackerone.com"}:
                raise ValueError
            parts = [p for p in url.path.split("/") if p]
            if not parts or len(parts) > 2 or len(parts) == 2 and parts[1].lower() not in _H1_SUFFIXES:
                raise ValueError
            handle = parts[0]
        except ValueError:
            raise ScopeError(_H1_BAD, "invalid_h1_input") from None
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", handle) or handle.lower() in _H1_RESERVED:
        raise ScopeError("Handle HackerOne không hợp lệ. " + _H1_BAD, "invalid_h1_input")
    return handle.lower()


def classify(value: str, kind="in", asset_type: str | None = None, instruction="") -> ScopeEntry:
    value = value.strip()
    if not value or len(value) > 4096 or any(ord(c) < 32 for c in value):
        raise ScopeError("Empty, oversized or multiline scope entry")
    declared = (asset_type or "").upper()
    try:
        if declared == "SOURCE_CODE" or value.startswith("repo:"):
            # Keep resource scope, never grant all of a code host for one repository.
            pattern, category, inferred = "repo:" + normalize_repo(value.removeprefix("repo:")), "source_code", "SOURCE_CODE"
        elif declared in {"GOOGLE_PLAY_APP_ID", "APPLE_STORE_APP_ID", "ANDROID", "IOS"} or value.startswith("app:"):
            pattern, category, inferred = value, "mobile", "mobile"
        elif declared and declared not in {"URL", "DOMAIN", "WILDCARD", "IP", "IP_ADDRESS", "CIDR", "WEB"}:
            pattern, category, inferred = value, "other", "other"
        else:
            try:
                addr = ipaddress.ip_address(value)
            except ValueError:
                addr = None
            if addr is not None:
                pattern, category, inferred = str(addr), "ip", "ip"
            elif "/" in value and "://" not in value:
                pattern, category, inferred = str(ipaddress.ip_network(value, strict=True)), "cidr", "cidr"
            elif value.startswith("*."):
                pattern, category, inferred = normalize_pattern(value), "wildcard", "wildcard"
            elif kind == "out" and "*" in value and "/" not in value and ":" not in value:
                # "*label.example.com": cannot be expressed as an allow rule, but excluding it is always safe.
                pattern, category, inferred = normalize_pattern(value, deny=True), "wildcard", "wildcard"
            elif value.startswith(("http://", "https://")):
                normalize_host(value)
                pattern, category, inferred = value, "web", "url"
            elif "." in value:
                pattern, category, inferred = normalize_host(value), "web", "domain"
            else:
                pattern, category, inferred = value, "other", "other"
    except (ValueError, UnicodeError) as exc:
        raise ScopeError(f"Invalid scope entry: {value}") from exc
    return ScopeEntry(pattern=pattern, kind=kind, asset_type=asset_type or inferred,
                      category=category, instruction=instruction)


def raw_parse(lines: list[str], out_lines: list[str] = ()) -> tuple[list[ScopeEntry], list[str]]:
    from backend.jobs.scope_parse import entries_or_raise, parse_scope  # avoids a module cycle
    return entries_or_raise(parse_scope(lines, out_lines))


def raw_entries(lines: list[str], out_lines: list[str] = ()) -> list[ScopeEntry]:
    return raw_parse(lines, out_lines)[0]


def deduplicate(entries: list[ScopeEntry]) -> list[ScopeEntry]:
    return list({(entry.pattern, entry.kind): entry for entry in entries}.values())


def default_config(settings: Settings, entries: list[ScopeEntry]) -> ScanConfig:
    depth = settings.BBASM_DEFAULT_DEPTH
    return ScanConfig(
        depth=depth, threads=settings.BB_THREADS, rate_limit=settings.BB_RATE_LIMIT,
        scan_timeout=settings.scan_timeout(depth),
        nuclei_severity={"passive": "", "light": "low,medium", "strong": "low,medium,high,critical"}[depth],
        skip_nmap=depth != "strong", skip_nuclei=depth == "passive",
        skip_active_crawl=depth == "passive",
        categories_enabled=sorted({e.category for e in entries if e.kind == "in" and e.category not in {"mobile", "other"}}),
    )


def program_config(settings: Settings, conn, program, entries: list[ScopeEntry], depth: str | None = None) -> ScanConfig:
    """The starting configuration for a program: system defaults, then its default profile, then its saved request
    headers. Drafts and schedules both start here, so a program behaves the same whichever way it is launched.
    With `depth` (a schedule's chosen level) a profile of another depth is ignored rather than silently changing it."""
    config = default_config(settings.model_copy(update={"BBASM_DEFAULT_DEPTH": depth}) if depth else settings, entries)
    if program is None:
        return config
    if program["default_profile_id"]:
        saved = conn.execute("SELECT config_json FROM profile WHERE id=?", (program["default_profile_id"],)).fetchone()
        recipe = json.loads(saved[0]) if saved else None
        if recipe and (depth is None or recipe.get("depth") == depth):
            from backend.profiles import apply_recipe
            config = apply_recipe(config, recipe)  # scope selections stay the draft's own
    if program["request_headers_json"]:
        config = config.model_copy(update={"request_headers": json.loads(program["request_headers_json"])})
    from backend.scope_selection import apply_selection, read_selection
    return apply_selection(config, entries, read_selection(program["scope_selection_json"]))


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9.-]", "-", value.lower()).strip(".-")[:100].rstrip(".") or "raw"
    if slug.split(".")[0] in {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}:
        slug = "program-" + slug
    return slug


class ScopeResolver:
    def __init__(self, settings: Settings, database: Database, provider=None):
        self.settings, self.database = settings, database
        if provider is None:
            from backend.jobs.h1_scope import HackerOneScopeProvider
            provider = HackerOneScopeProvider(settings)
        self.provider = provider

    def resolve(self, request: ResolveRequest) -> ResolveResponse:
        source = "raw" if request.input == "raw" else "h1"
        handle = h1_handle(request.input) if source == "h1" else None
        if source == "h1" and (request.scope or request.scope_out):
            raise ScopeError("scope[] is only accepted with input=raw")
        parse_warnings = []
        entries = []
        if source == "raw":
            entries, parse_warnings = raw_parse(request.scope, request.scope_out)
        identity = handle or hashlib.sha256(json.dumps(sorted(
            (e.pattern, e.kind) for e in entries
        )).encode()).hexdigest()
        base = safe_slug(handle or "raw")
        if source == "raw" and len(entries) == 1 and entries[0].category in {"web", "wildcard", "ip"}:
            base = safe_slug(normalize_host(entries[0].pattern.removeprefix("*.")))
        if source == "raw" and (len(entries) != 1 or entries[0].category not in {"web", "wildcard", "ip"}):
            base = "raw-" + identity[:12]
        if source == "raw" and request.name.strip():
            base = safe_slug(request.name.strip())  # the user's own name wins over derived ones
        # Serialize resolves to protect program reuse and slug allocation. P2 jobs use
        # independent connections; resolve's bounded metadata fetch can hold this lock.
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                slug = base
                suffix = hashlib.sha256(f"{source}:{identity}".encode()).hexdigest()[:12]
                while True:
                    existing = conn.execute("SELECT * FROM program WHERE slug=?", (slug,)).fetchone()
                    if existing is None:
                        break
                    policy = json.loads(existing["policy_json"] or "{}")
                    if existing["source"] == source and (existing["handle"] == handle if handle else policy.get("scope_identity") == identity):
                        break
                    if slug != base:
                        raise ScopeError("Slug collision requires review", "slug_collision")
                    slug = f"{base}-{suffix}"
                target_dir = self.settings.BBASM_TARGETS / slug
                target_dir = target_dir.resolve()
                if not target_dir.is_relative_to(self.settings.BBASM_TARGETS.resolve()):
                    raise ScopeError("Target directory escapes configured root")
                audit_path = target_dir / "audit.jsonl"
                warnings = []
                if source == "h1":
                    entries, policy, warnings = self.provider.resolve(handle, audit_path)
                    entries = deduplicate(entries)
                else:
                    policy = {"scope_identity": identity, "assets": [e.model_dump() for e in entries]}
                    warnings = parse_warnings
                if request.policy_text.strip():
                    policy["user_policy_text"] = request.policy_text.strip()
                elif existing is not None:
                    # Re-resolving (e.g. "Scan lại") must not erase the policy the user pasted in earlier.
                    kept = json.loads(existing["policy_json"] or "{}").get("user_policy_text")
                    if kept:
                        policy["user_policy_text"] = kept
                if not any(entry.kind == "in" for entry in entries):
                    raise ScopeError("scope empty", "scope_empty")
                now = utc_now()
                if existing is None:
                    program_id = conn.execute(
                        "INSERT INTO program(slug,source,handle,platform,policy_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                        (slug, source, handle, "h1" if handle else None, json.dumps(policy), now, now),
                    ).lastrowid
                else:
                    program_id = existing["id"]
                    conn.execute("UPDATE program SET policy_json=?,updated_at=? WHERE id=?", (json.dumps(policy), now, program_id))
                if existing is None:
                    # An existing program may be scheduled from its stored scope_rule rows. A draft
                    # the user has not confirmed must not rewrite them; launch applies the snapshot.
                    conn.executemany("INSERT INTO scope_rule(program_id,pattern,kind,asset_type) VALUES(?,?,?,?)", [
                        (program_id, e.pattern, e.kind, e.asset_type) for e in entries
                    ])
                config = program_config(self.settings, conn, existing, entries)
                scan_id = conn.execute("INSERT INTO scan_run(program_id,depth,status,trigger,stats_json) VALUES(?,?,'draft','manual',?)", (
                    program_id, config.depth, json.dumps({"resolved_scope": [e.model_dump() for e in entries], "warnings": warnings,
                                "launch_gate": launch_gate(source, policy),
                                # The policy this draft was resolved with. Review, the header check and launch use it, so a
                                # newer Resolve of the same program cannot change what an older draft is judged against.
                                "policy_snapshot": policy, "policy_snapshot_at": now}),
                )).lastrowid
                conn.execute(
                    "INSERT INTO scan_config(scan_run_id,depth,threads,rate_limit,scan_timeout,nuclei_severity,skip_nmap,skip_nuclei,skip_active_crawl,categories_enabled_json,excluded_hosts_json,options_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (scan_id, config.depth, config.threads, config.rate_limit, config.scan_timeout,
                     config.nuclei_severity, config.skip_nmap, config.skip_nuclei, config.skip_active_crawl,
                     json.dumps(config.categories_enabled), json.dumps(config.excluded_hosts), json.dumps(config.options()), now),
                )
                target_dir.mkdir(parents=True, exist_ok=True)
                if existing is None:
                    scope_text = "# IN\n" + "\n".join(e.pattern for e in entries if e.kind == "in") + "\n# OUT\n" + "\n".join(e.pattern for e in entries if e.kind == "out") + "\n"
                    # A scan-specific snapshot in DB is authoritative; .scope is the latest preview.
                    temp_scope = target_dir / ".scope.tmp"
                    with temp_scope.open("w", encoding="utf-8", newline="\n") as stream:
                        stream.write(scope_text)
                    temp_scope.replace(target_dir / ".scope")
                audit(audit_path, slug, "draft", "scope_resolved", scan_id=scan_id)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        groups = defaultdict(list)
        for entry in entries:
            groups[entry.category].append(entry)
        return ResolveResponse(scan_id=scan_id, slug=slug, config=config,
                               assets_by_category=dict(groups), warnings=warnings)
