"""Build framework commands from the approved per-scan scope snapshot."""

from dataclasses import dataclass, field
import json
import ipaddress
import os
from pathlib import Path
import shutil
from uuid import uuid4
from urllib.parse import urlsplit

from backend.framework import load_module
from backend.models import ScanConfig, ScopeEntry
from backend.scope_gate import ScopeGate, audit, normalize_host, normalize_pattern


class EgressUnavailable(RuntimeError):
    pass


class AuditedEgress:
    """Audit approved command launches; this is not network isolation."""

    def check(self, plan, command):
        audit(plan.audit_path, command.category, "allow", "audited_spawn",
              scan_id=plan.scan_id, resource=command.resource)


class ClosedEgress:
    """Operator kill switch: deny tool launches before creating a process."""

    def check(self, plan, command):
        audit(plan.audit_path, command.category, "deny", "recon_disabled", scan_id=plan.scan_id)
        raise EgressUnavailable("Live recon disabled: BBASM_RECON_DISABLED is enabled")


@dataclass
class Command:
    argv: list[str]
    env: dict[str, str]
    output: Path
    category: str = "web"
    resource: str | None = None


@dataclass
class ReconPlan:
    scan_id: int
    program_id: int
    slug: str
    config: ScanConfig
    root: Path
    audit_path: Path
    gate: ScopeGate
    commands: list[Command] = field(default_factory=list)
    discoveries: list[Command] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def read_config(row):
    return ScanConfig(**{key: row[key] for key in (
        "depth", "threads", "rate_limit", "scan_timeout", "nuclei_severity",
        "skip_nmap", "skip_nuclei", "skip_active_crawl")},
        categories_enabled=json.loads(row["categories_enabled_json"]),
        excluded_hosts=json.loads(row["excluded_hosts_json"]),
        **json.loads(row["options_json"] or "{}"))


def recon_env(settings, config, output, *, discovery=False, skip_historical=False):
    passive = config.depth == "passive" or discovery
    # Inherited tool toggles, auth sessions, shell init and proxies must not override review.
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "SYSTEMROOT", "SystemRoot", "TMP", "TEMP", "LANG"}}
    env.update({
        "PATH": settings.tool_search_path(),
        "HOME": os.environ.get("HOME") or str(Path.home()),
        "BBASM_SKIP_HISTORICAL": str(int(settings.BBASM_SKIP_HISTORICAL or skip_historical or config.skip_historical)),
        "BBASM_HISTORICAL_TIMEOUT": str(settings.BBASM_HISTORICAL_TIMEOUT),
        "BBASM_BBROOT": str(settings.BBASM_BBROOT), "BBASM_TOOLS_SUBDIR": settings.BBASM_TOOLS_SUBDIR,
        "RECON_OUT_DIR": str(output), "SECRETS_OUT_DIR": str(output),
        "BBHUNT_DASHBOARD": "1", "BBASM_MANAGED": "1",
        "BB_THREADS": str(config.threads), "BB_RATE_LIMIT": str(config.rate_limit),
        "NUC_CONCURRENCY": str(config.threads), "NUC_RATE_LIMIT": str(config.rate_limit),
        "BBASM_SKIP_NMAP": str(int(passive or config.depth == "light" or config.skip_nmap)),
        "BBASM_SKIP_HTTPX": str(int(passive)),
        "BBASM_SKIP_ACTIVE_CRAWL": str(int(passive or config.skip_active_crawl)),
        "BBASM_SKIP_NUCLEI": str(int(passive or config.skip_nuclei)),
        "BBASM_NUC_SEV": config.nuclei_severity,
        "BBASM_SKIP_FFUF": str(int(config.depth != "strong" or config.skip_ffuf)),
        "BBASM_SKIP_CICD": "1",  # No automatic org expansion from discovered links.
        "BBASM_NMAP_CONNECT": "1",  # Portable -sT, including WSL2/no raw capabilities.
    })
    for key in ("CHAOS_KEY", "GITHUB_TOKEN"):
        if getattr(settings, key).get_secret_value():
            env[key] = getattr(settings, key).get_secret_value()
    for key in ("BBASM_NO_INTERACTSH", "BBASM_NO_REDIRECT", "BBASM_SCOPE_CRAWL", "BBASM_NO_VERIFY"):
        env[key] = str(int(getattr(settings, key)))
    return env


class ReconOrchestrator:
    def __init__(self, settings, database):
        self.settings, self.database = settings, database

    def build(self, scan_id):
        with self.database.connect() as conn:
            scan = conn.execute("SELECT s.*,p.slug FROM scan_run s JOIN program p ON p.id=s.program_id WHERE s.id=?", (scan_id,)).fetchone()
            config = read_config(conn.execute("SELECT * FROM scan_config WHERE scan_run_id=?", (scan_id,)).fetchone())
        entries = [ScopeEntry(**item) for item in json.loads(scan["stats_json"])["resolved_scope"]]
        target = (self.settings.BBASM_TARGETS / scan["slug"]).resolve()
        if not target.is_relative_to(self.settings.BBASM_TARGETS.resolve()):
            raise ValueError("Target path escaped root")
        eligible = [e for e in entries if e.category not in {"mobile", "other"}]
        allow = [e.pattern for e in eligible if e.kind == "in" and e.category in config.categories_enabled]
        deny = [e.pattern for e in eligible if e.kind == "out"] + config.excluded_hosts
        gate = ScopeGate(allow, deny, target / "audit.jsonl", self.settings)
        root = target / "recon" / "scans" / str(scan_id)
        warnings = self._claim_output(scan_id, root)
        plan = ReconPlan(scan_id, scan["program_id"], scan["slug"], config, root, target / "audit.jsonl", gate)
        plan.warnings.extend(warnings)
        seeds = []
        for entry in entries:
            if entry.kind != "in":
                continue
            if entry.category in {"mobile", "other"}:
                plan.warnings.append(f"Manual asset: {entry.pattern}")
                continue
            if entry.category not in config.categories_enabled:
                continue
            if normalize_pattern(entry.pattern) in gate.deny:
                continue
            if entry.category == "wildcard":
                # Enumerate only, then filter discoveries before any active command.
                command = self._recon(plan, entry.pattern[2:], discovery=True)
                if command:
                    plan.discoveries.append(command)
            elif gate.in_scope(entry.pattern):
                if entry.category == "source_code":
                    self._source(plan, entry.pattern)
                elif entry.category == "cidr":
                    self._recon(plan, entry.pattern, target_type="cidr")
                else:
                    seeds.append(normalize_host(entry.pattern))
        if seeds:
            self._host_list(plan, seeds)
        return plan

    def _claim_output(self, scan_id, root):
        # Persist ownership before touching files. A failed build must be retried
        # with a new scan, not allowed to ingest potentially stale partial output.
        with self.database.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT stats_json,status FROM scan_run WHERE id=?", (scan_id,)).fetchone()
            stats = json.loads(row[0] or "{}")
            if row["status"] not in {"draft", "queued"}:
                raise ValueError("Scan output already owned by an executed scan")
            if stats.get("output_claim"):
                raise ValueError("Scan output already claimed; create a new scan")
            # Legacy completed/running scans with evidence of execution remain
            # owned even though they predate output_claim.
            if any(key in stats for key in ("diff_baseline", "diff_complete", "observations")):
                raise ValueError("Scan output already exists for an executed scan")
            stats["output_claim"] = uuid4().hex
            conn.execute("UPDATE scan_run SET stats_json=? WHERE id=?", (json.dumps(stats), scan_id))
        if any(path.is_symlink() for path in (root, *root.parents)):
            raise ValueError("Refusing scan output symlink")
        warnings = []
        if root.exists():
            archive = root.with_name(f".orphan-{scan_id}-{uuid4().hex}")
            root.rename(archive)
            warnings.append(f"Preserved orphan scan output at {archive.name}")
        root.mkdir(parents=True)
        return warnings

    def _recon(self, plan, target, discovery=False, target_type=None, skip_historical=False):
        script = self.settings.tool_path("recon_engine.sh")
        if not script.is_file():
            plan.warnings.append("recon_engine.sh missing; skipping")
            return None
        output = plan.root / str(len(plan.commands))
        env = recon_env(self.settings, plan.config, output, discovery=discovery,
                        skip_historical=skip_historical or target_type in {"ip", "cidr"})
        if target_type:
            env["TARGET_TYPE"] = target_type
        argv = ["bash", str(script), str(target)]
        if discovery or plan.config.depth != "strong":
            argv.append("--quick")
        command = Command(argv, env, output, resource=str(target))
        plan.commands.append(command)
        return command

    def _host_list(self, plan, hosts):
        input_dir = plan.root.parent.parent.parent / ".inputs" / str(plan.scan_id)
        input_dir.mkdir(parents=True, exist_ok=True)
        path = input_dir / f"hosts-{len(plan.commands)}.txt"
        path.write_text("\n".join(sorted(set(hosts))) + "\n", encoding="utf-8", newline="\n")
        def is_ip(host):
            try:
                ipaddress.ip_address(host)
                return True
            except ValueError:
                return False
        return self._recon(plan, path, skip_historical=all(is_ip(host) for host in hosts))

    def _source(self, plan, resource):
        script = self.settings.tool_path("secrets_hunter.sh")
        if not script.is_file():
            plan.warnings.append("secrets_hunter.sh missing; skipping source_code")
            return
        if plan.config.depth == "passive":
            plan.warnings.append("source_code remains manual at passive depth; repository fetching requires active depth")
            return
        url = resource.removeprefix("repo:")
        if urlsplit(url).netloc != "github.com":
            plan.warnings.append(f"Repo ngoài GitHub chỉ được ghi nhận để làm tay, không tự clone: {url}")
            return
        path = urlsplit(url).path.strip("/")
        output = plan.root / str(len(plan.commands))
        flag, value = ("--github-org", path) if "/" not in path else ("--git", url)
        plan.commands.append(Command(["bash", str(script), flag, value, "--out", str(output)],
            recon_env(self.settings, plan.config, output), output, "source_code", resource))

    def discovered_commands(self, plan):
        if plan.config.depth == "passive":
            return []
        adapter = load_module(self.settings, "recon_adapter.py")
        hosts = set()
        for command in plan.discoveries:
            for host in adapter.ReconAdapter(command.output).get_subdomains():
                if plan.gate.in_scope(host):
                    hosts.add(normalize_host(host))
        command = self._host_list(plan, hosts) if hosts else None
        return [command] if command else []

    def missing_tools(self):
        return [name for name in ("subfinder", "httpx", "nuclei", "nmap", "katana", "gau", "amass", "ffuf")
                if shutil.which(name, path=self.settings.tool_search_path()) is None]
