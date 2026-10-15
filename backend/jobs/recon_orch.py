"""Build framework commands from the approved per-scan scope snapshot."""

from dataclasses import dataclass, field
import json
import ipaddress
import os
from pathlib import Path
import re
import shlex
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
    stage: str = "main"            # discovery | probe | main | deep | source | monitor
    hosts: tuple = ()               # hosts this command is responsible for (probe/deep batches)


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
    explicit_hosts: set = field(default_factory=set)       # hosts named in the scope (not discovered)
    tool_notes: list = field(default_factory=list)         # behaviour a wrapper changed (e.g. katana known-files off)
    sources: list = field(default_factory=list)            # outcome of each passive source: [{source,status,seconds,stage}]
    stages: list = field(default_factory=list)             # [{key,label,status,budget_s,used_s,commands}]
    coverage: dict = field(default_factory=lambda: {"discovered": 0, "probed": 0, "unprobed": 0, "explicit": 0, "batches": 0, "batches_done": 0})
    probed_hosts: set = field(default_factory=set)         # hosts whose probe batch finished
    path_rules: dict = field(default_factory=dict)         # host -> OUT paths (rules the crawlers cannot honour)


def read_config(row):
    return ScanConfig(**{key: row[key] for key in (
        "depth", "threads", "rate_limit", "scan_timeout", "nuclei_severity",
        "skip_nmap", "skip_nuclei", "skip_active_crawl")},
        categories_enabled=json.loads(row["categories_enabled_json"]),
        excluded_hosts=json.loads(row["excluded_hosts_json"]),
        **json.loads(row["options_json"] or "{}"))


SHIM_DIR = Path(__file__).resolve().parent.parent / "shims"
# Same semantics as coreutils timeout; the only difference is that the command word katana/curl/subfinder runs our wrapper.
TIMEOUT_FUNCTION = """() {  local a=("$@") i=0
    while [ "$i" -lt "${#a[@]}" ]; do
        case "${a[$i]}" in
            -k|-s|--kill-after|--signal) i=$((i+2)) ;;
            -*) i=$((i+1)) ;;
            *) break ;;
        esac
    done
    i=$((i+1))
    case "${a[$i]:-}" in katana|curl|subfinder) a[$i]="$BBASM_SHIM_DIR/${a[$i]}" ;; esac
    command timeout "${a[@]}"
}"""


def recon_env(settings, config, output, *, discovery=False, skip_historical=False, probe_only=False):
    passive = config.depth == "passive" or discovery
    # Inherited tool toggles, auth sessions, shell init and proxies must not override review.
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "SYSTEMROOT", "SystemRoot", "TMP", "TEMP", "LANG"}}
    env.update({
        # Bounded curl/subfinder wrappers first: the pinned scripts call them with no time limit.
        "PATH": os.pathsep.join([str(SHIM_DIR), settings.tool_search_path()]),
        "BBASM_SOURCE_TIMEOUT": str(settings.BBASM_SOURCE_TIMEOUT),
        "BBASM_SUBFINDER_TIMEOUT": str(settings.BBASM_SUBFINDER_TIMEOUT),
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
    env["BBASM_SHIM_DIR"] = str(SHIM_DIR)
    for tool in ("curl", "subfinder", "katana"):   # exported shell functions beat the engine's own PATH rewriting
        env[f"BASH_FUNC_{tool}%%"] = f'() {{  {shlex.quote(str(SHIM_DIR / tool))} "$@"\n}}'
    # `timeout 300 katana ...` execs the binary directly, past any function. Resolve the wrapped tool names here.
    env["BASH_FUNC_timeout%%"] = TIMEOUT_FUNCTION
    if probe_only:
        # Probe stage: liveness and fingerprint only. No archives, crawling, config-file checks, templates or fuzzing.
        env.update(BBASM_SKIP_HISTORICAL="1", BBASM_SKIP_ACTIVE_CRAWL="1", BBASM_SKIP_NUCLEI="1", BBASM_SKIP_FFUF="1")
    if config.request_headers and not passive:
        # Only commands that actually reach the target carry the policy header; discovery and passive never do.
        env["BBHUNT_AUTH_HEADERS"] = "\n".join(config.request_headers)
    for key in ("CHAOS_KEY", "GITHUB_TOKEN"):
        if getattr(settings, key).get_secret_value():
            env[key] = getattr(settings, key).get_secret_value()
    for key in ("BBASM_NO_INTERACTSH", "BBASM_NO_REDIRECT", "BBASM_SCOPE_CRAWL", "BBASM_NO_VERIFY"):
        env[key] = str(int(getattr(settings, key)))
    return env


SOURCE_FILES = ("subfinder.txt", "amass.txt", "crtsh.txt", "wayback_subs.txt")
_HOSTNAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+")


def _read_names(path, limit=2_000_000):
    if not path.is_file() or path.is_symlink():
        return
    with path.open(encoding="utf-8", errors="replace") as stream:
        for count, line in enumerate(stream):
            if count >= limit:
                return
            name = line.strip().lower()
            if name and len(name) <= 253 and _HOSTNAME.fullmatch(name):
                yield name


def subdomain_candidates(root):
    """(hosts, merged). The engine merges its sources into subdomains/all.txt only at the very end of discovery,
    so a command stopped earlier leaves subfinder/crt.sh/Wayback files and no all.txt. Use the merged file when
    it exists, otherwise whatever the individual sources already wrote."""
    base = Path(root) / "subdomains"
    merged = set(_read_names(base / "all.txt"))
    if merged:
        return sorted(merged), True
    names = set()
    for filename in SOURCE_FILES:
        names.update(_read_names(base / filename))
    return sorted(names), False


def read_tool_notes(root):
    """What a wrapper changed in a tool's behaviour for this command (shown to the user, never hidden)."""
    path = Path(root) / ".tool_notes.tsv"
    if not path.is_file() or path.is_symlink():
        return []
    notes = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:20]:
        tool, _, text = line.partition("\t")
        if re.fullmatch(r"[a-z]{2,20}", tool) and text.strip():
            notes.append({"tool": tool, "note": text.strip()[:300]})
    return notes


def nuclei_templates_ready(settings):
    """True when nuclei has at least one template to run. A present binary without templates tests nothing."""
    home = Path(os.environ.get("HOME") or Path.home())
    for base in (home / "nuclei-templates", home / ".local" / "nuclei-templates"):
        if base.is_dir() and next(base.rglob("*.yaml"), None) is not None:
            return True
    return False


_SOURCE_STATUS = {"ok", "timeout", "error"}


def read_source_status(root):
    """Outcome of each passive source as recorded by the curl/subfinder shims (host/tool + outcome, never content)."""
    path = Path(root) / ".source_status.tsv"
    rows = []
    if not path.is_file() or path.is_symlink():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:100]:
        parts = line.split("\t")
        if len(parts) != 4 or parts[1] not in _SOURCE_STATUS or not re.fullmatch(r"[A-Za-z0-9.-]{1,80}", parts[0]):
            continue
        try:
            rows.append({"source": parts[0], "status": parts[1], "seconds": int(parts[2]), "exit": int(parts[3])})
        except ValueError:
            continue
    return rows


def lines_of(path):
    if path.is_file() and not path.is_symlink():
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if line.strip():
                    yield line.strip()


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
        plan.path_rules = gate.path_rule_hosts()
        self._path_rule_notes(plan)
        if seeds:
            plan.explicit_hosts = set(seeds)
            plan.coverage["explicit"] = len(seeds)
            restricted = [h for h in seeds if self._probe_only_host(plan, h)]
            free = [h for h in seeds if h not in restricted]
            if free:
                self._host_list(plan, free)
            if restricted:   # same stage, but liveness/fingerprint only
                self._host_list(plan, restricted, probe_only=True)
        return plan

    @staticmethod
    def _probe_only_host(plan, host):
        return host in plan.path_rules and not plan.config.allow_active_on_path_rules

    @staticmethod
    def _path_rule_notes(plan):
        for host, paths in sorted(plan.path_rules.items()):
            sample = ", ".join(paths[:2]) + ("…" if len(paths) > 2 else "")
            if plan.config.allow_active_on_path_rules:
                plan.warnings.append(f"{host}: {len(paths)} OUT theo đường dẫn ({sample}). Bạn đã cho phép công cụ chủ động: "
                                     "URL OUT bị lọc khỏi kết quả nhưng crawler/nuclei có thể đã gửi request tới đó")
            else:
                plan.warnings.append(f"{host}: {len(paths)} OUT theo đường dẫn ({sample}). Crawl/nuclei/ffuf không thi hành được "
                                     "loại trừ theo đường dẫn nên host này chỉ được probe")

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

    def _recon(self, plan, target, discovery=False, target_type=None, skip_historical=False, stage=None, probe_only=False, hosts=()):
        script = self.settings.tool_path("recon_engine.sh")
        if not script.is_file():
            plan.warnings.append("recon_engine.sh missing; skipping")
            return None
        output = plan.root / str(len(plan.commands))
        env = recon_env(self.settings, plan.config, output, discovery=discovery, probe_only=probe_only,
                        skip_historical=skip_historical or target_type in {"ip", "cidr"})
        if target_type:
            env["TARGET_TYPE"] = target_type
        argv = ["bash", str(script), str(target)]
        if discovery or plan.config.depth != "strong":
            argv.append("--quick")
        command = Command(argv, env, output, resource=str(target),
                          stage=stage or ("discovery" if discovery else "main"), hosts=tuple(hosts))
        plan.commands.append(command)
        return command

    def _host_list(self, plan, hosts, stage="main", probe_only=False):
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
        return self._recon(plan, path, skip_historical=all(is_ip(host) for host in hosts), stage=stage,
                           probe_only=probe_only, hosts=sorted(set(hosts)))

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

    def discovered_hosts(self, plan):
        """In-scope hosts found by the discovery commands, minus hosts the scope already names. Shallow names first."""
        if plan.config.depth == "passive":
            return []
        found = set()
        for command in plan.discoveries:
            names, _ = subdomain_candidates(command.output)
            for name in names:
                if name not in plan.explicit_hosts and plan.gate.in_scope(name):
                    found.add(normalize_host(name))
        return sorted(found, key=lambda host: (host.count("."), host))

    def probe_batches(self, plan, hosts):
        """Probe-only commands (liveness + fingerprint) in batches, so a time limit leaves some hosts probed instead
        of none, and the report can say exactly how many were not reached."""
        if plan.config.depth == "passive" or not hosts:
            return []
        size = self.settings.BBASM_PROBE_BATCH
        plan.coverage["discovered"] = len(hosts)
        batches = [self._host_list(plan, hosts[i:i + size], stage="probe", probe_only=True) for i in range(0, len(hosts), size)]
        batches = [batch for batch in batches if batch]
        plan.coverage["batches"] = len(batches)
        return batches

    def deep_command(self, plan, probe_commands):
        """The configured Light/Strong pass (crawl, JS, templates) for the best live discovered hosts."""
        if plan.config.depth == "passive":
            return None
        ranked = []
        for command in probe_commands:
            if not command.hosts or not set(command.hosts) <= plan.probed_hosts:
                continue
            for line in lines_of(command.output / "live" / "httpx_full.txt"):
                match = re.match(r"(\S+)\s+\[(\d{3})\]", line)
                if not match:
                    continue
                host = urlsplit(match.group(1)).hostname
                if host and host not in plan.explicit_hosts and not self._probe_only_host(plan, host) and plan.gate.in_scope(host):
                    status = int(match.group(2))
                    ranked.append((0 if status == 200 else 1 if status < 400 else 2, host.count("."), normalize_host(host)))
        chosen = []
        for _, _, host in sorted(ranked):
            if host not in chosen:
                chosen.append(host)
            if len(chosen) >= self.settings.BBASM_DEEP_HOSTS:
                break
        return self._host_list(plan, chosen, stage="deep") if chosen else None

    def missing_tools(self):
        missing = [name for name in ("subfinder", "httpx", "nuclei", "nmap", "katana", "gau", "amass", "ffuf")
                   if shutil.which(name, path=self.settings.tool_search_path()) is None]
        if "nuclei" not in missing and not nuclei_templates_ready(self.settings):
            missing.append("nuclei-templates")     # the binary alone checks nothing
        return missing
