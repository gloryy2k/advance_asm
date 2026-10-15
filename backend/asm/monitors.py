"""Scope-filtered framework monitors and redacted, idempotent finding ingestion."""
import hashlib
import json
import re
import shutil
from urllib.parse import urlsplit

from backend.jobs.ingest import lines
from backend.jobs.recon_orch import Command, recon_env
from backend.scope_gate import normalize_host


class Monitors:
    def __init__(self, settings, database):
        self.settings, self.database = settings, database

    def available(self, *names):
        return any(shutil.which(n, path=self.settings.tool_search_path()) for n in names)

    def commands(self, plan):
        if plan.config.depth == "passive":
            return []
        hosts, bundles = set(), set()
        for command in plan.commands:
            if command.category != "web" or not command.output.exists():
                continue
            if any(p.is_symlink() for p in command.output.rglob("*")) or command.output.is_symlink():
                raise ValueError("Symlinks are not accepted in monitor input")
            hosts.update(h for h in lines(command.output / "subdomains/all.txt")
                         if h not in plan.path_rules and plan.gate.in_scope(h))
            bundles.update(u for u in lines(command.output / "urls/js_files.txt")
                           if urlsplit(u).scheme in {"http", "https"}
                           and urlsplit(u).hostname not in plan.path_rules and plan.gate.in_scope(u))
        root = plan.root / "monitors"
        commands = []
        # User choices: skip a monitor entirely, or cap how many JS bundles get downloaded.
        bundles = set(sorted(bundles)[:plan.config.max_js_files])
        for kind, filename, values, relative, flag, tools in (
            ("takeover", "takeover_scanner.sh", hosts, "subdomains/all.txt", "--recon", ("dnsreaper", "subjack")),
            ("secret", "secrets_hunter.sh", bundles, "urls/js_files.txt", "--js-bundle", ("trufflehog", "noseyparker")),
        ):
            script = self.settings.tool_path(filename)
            if not values or not script.is_file() or not self.available(*tools):
                continue
            if (kind == "takeover" and plan.config.skip_takeover) or (kind == "secret" and plan.config.skip_secrets):
                continue
            inputs, output = root / "input", root / kind
            path = inputs / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(sorted(values)) + "\n", encoding="utf-8", newline="\n")
            env = recon_env(self.settings, plan.config, output)
            env["TAKEOVER_OUT_DIR"] = str(output)
            commands.append(Command(["bash", str(script), flag, str(inputs)], env, output, kind, str(inputs)))
        return commands

    def ingest(self, plan):
        records = []
        root = plan.root / "monitors"
        if root.exists() and (root.is_symlink() or any(p.is_symlink() for p in root.rglob("*"))):
            raise ValueError("Symlinks are not accepted in monitor output")

        def add(target, kind, severity, name, detail):
            if target and not plan.gate.in_scope(target):
                return
            records.append((normalize_host(target) if target else None, kind, severity, name, detail))

        def rows(path):
            if path.suffix == ".json":
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    return data if isinstance(data, list) else []
                except (OSError, ValueError):
                    return []
            result = []
            for line in lines(path):
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        result.append(row)
                except ValueError:
                    pass
            return result

        for row in rows(root / "takeover/dnsreaper.json"):
            if not isinstance(row, dict):
                continue
            target = row.get("domain") or row.get("host") or row.get("subdomain")
            if target:
                add(target, "takeover", "high", "dnsreaper:" + str(row.get("service") or row.get("signature") or "candidate"), {"source": "dnsreaper", "candidate": True})
        for filename in ("subjack.txt", "fingerprint_grep.txt"):
            for line in lines(root / "takeover" / filename):
                # subjack prints "[SERVICE] host"; grep fallback prints "host service".
                candidates = re.findall(r"(?:[a-zA-Z0-9-]+\.)+[a-zA-Z0-9-]+", line)
                if candidates:
                    add(candidates[0], "takeover", "high", filename + ":candidate", {"source": filename, "candidate": True})
        for filename in ("trufflehog.jsonl", "noseyparker.jsonl", "gitleaks.json"):
            for row in rows(root / "secret" / filename):
                if not isinstance(row, dict):
                    continue
                verified = row.get("Verified") is True
                detector = str(row.get("DetectorName") or row.get("RuleID") or row.get("rule_name") or "secret")
                # The pinned downloader translates URL punctuation into underscores.
                # Associate only a unique filename match, never guess across bundles.
                target = None
                metadata = row.get("SourceMetadata") or {}
                try:
                    source_file = metadata["Data"]["Filesystem"]["file"].replace("\\", "/").split("/")[-1]
                    matches = [url for url in lines(root / "input/urls/js_files.txt")
                               if re.sub(r"[/?:&=#]", "_", url)[:200] + ".js" == source_file]
                    if len(matches) == 1:
                        target = matches[0]
                except (KeyError, TypeError, AttributeError):
                    pass
                add(target, "secret", "high" if verified else "medium", detector,
                    {"source": filename, "verified": verified})
        for line in lines(root / "secret/regex_hits.txt"):
            digest = hashlib.sha256(line.encode()).hexdigest()[:16]
            add(None, "secret", "medium", "regex:" + digest, {"source": "regex", "verified": False})
        for command in plan.commands:
            if command.category != "web":
                continue
            for endpoint in lines(command.output / "js/endpoints.txt"):
                if endpoint.startswith(("http://", "https://")):
                    add(endpoint, "js-endpoint", "info", endpoint, {"endpoint": endpoint})
                elif endpoint.startswith("/") and not endpoint.startswith("//"):
                    add(None, "js-endpoint", "info", endpoint, {"endpoint": endpoint})

        with self.database.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            for host, kind, severity, name, detail in records:
                row = conn.execute("SELECT id FROM asset WHERE program_id=? AND host=?", (plan.program_id, host)).fetchone() if host else None
                asset_id = row[0] if row else None
                # SQLite UNIQUE permits multiple NULLs, so explicitly match IS NULL.
                existing = conn.execute("SELECT id FROM finding WHERE program_id=? AND type=? AND name=? AND asset_id IS ?",
                                        (plan.program_id, kind, name, asset_id)).fetchone()
                if existing:
                    conn.execute("UPDATE finding SET severity=?,detail_json=?,last_seen_scan=? WHERE id=?",
                                 (severity, json.dumps(detail), plan.scan_id, existing[0]))
                else:
                    conn.execute("INSERT INTO finding(program_id,asset_id,type,severity,name,detail_json,first_seen_scan,last_seen_scan) VALUES(?,?,?,?,?,?,?,?)",
                                 (plan.program_id, asset_id, kind, severity, name, json.dumps(detail), plan.scan_id, plan.scan_id))
            return conn.execute("SELECT count(*) FROM finding WHERE program_id=? AND last_seen_scan=? AND type IN ('takeover','secret','js-endpoint')",
                                (plan.program_id, plan.scan_id)).fetchone()[0]
