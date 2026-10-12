"""Idempotent ingestion of scoped framework output, including partial scans."""

import json
import re

from backend.framework import load_module
from backend.scope_gate import normalize_host

SEVERITIES = {"info", "low", "medium", "high", "critical"}


def lines(path):
    if path.is_file():
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if line.strip():
                    yield line.strip()


def httpx_record(line):
    if line.startswith("{"):
        row = json.loads(line)
        return row.get("url") or row.get("input"), row.get("status_code"), row.get("title"), row.get("tech") or [], row.get("host_ip")
    url = line.split()[0]
    blocks = re.findall(r"\[([^\]]*)\]", line[len(url):])
    status = None
    if blocks and re.fullmatch(r"\d{3}(?:,\d{3})*", blocks[0]):
        status = int(blocks.pop(0).split(",")[-1])
    if blocks and blocks[0].isdigit():
        blocks.pop(0)  # content length
    title = blocks[0] if blocks else None
    tech = [value.strip() for value in blocks[-1].split(",")] if len(blocks) > 1 else []
    return url, status, title, tech, None


class Ingester:
    def __init__(self, settings, database):
        self.settings, self.database = settings, database

    def ingest(self, plan):
        module = load_module(self.settings, "recon_adapter.py")
        assets, urls, findings = {}, {}, []

        def asset(resource, category="web", **details):
            if not isinstance(resource, str) or not plan.gate.in_scope(resource):
                return None
            host = resource if category == "source_code" else normalize_host(resource)
            row = assets.setdefault(host, {"category": category})
            row.update({key: value for key, value in details.items() if value is not None})
            return host

        for command in plan.commands:
            root = command.output
            if not root.is_dir():
                continue
            # Reject output symlinks before letting the framework adapter read them.
            if any(path.is_symlink() for path in root.rglob("*")) or root.is_symlink():
                raise ValueError("Symlinks are not accepted in recon output")
            if command.category == "source_code":
                for filename in ("trufflehog.jsonl", "noseyparker.jsonl", "gitleaks.json"):
                    path = root / filename
                    rows = []
                    if filename.endswith(".json") and path.is_file():
                        try:
                            rows = json.loads(path.read_text(encoding="utf-8"))
                        except ValueError:
                            continue
                    else:
                        for line in lines(path):
                            try:
                                rows.append(json.loads(line))
                            except ValueError:
                                continue
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        host = asset(command.resource, "source_code")
                        if host:
                            name = str(row.get("DetectorName") or row.get("RuleID") or row.get("rule_name") or "secret")
                            # Do not copy raw credential strings into the dashboard DB/logs.
                            findings.append((host, "secret", "high" if row.get("Verified") is True else "medium", name,
                                             {"source": filename, "verified": row.get("Verified") is True}))
                continue
            canonical = module.load_recon(root.name, recon_dir=root.parent)
            nested = module.ReconAdapter(root)
            for host in set(canonical.subdomains + nested.get_subdomains()):
                asset(host, "ip" if ":" in host or re.fullmatch(r"[0-9.]+", host) else "web")
            for url in set(canonical.live_hosts + nested.get_live_hosts()):
                if host := asset(url):
                    urls[url] = (host, "httpx")
            for line in lines(root / "live" / "httpx_full.txt"):
                try:
                    url, status, title, tech, ip = httpx_record(line)
                    asset(url, status_code=status, title=title, tech=tech, ip=ip)
                except (ValueError, TypeError, IndexError):
                    continue
            for url in set(canonical.urls + nested.get_urls()):
                if host := asset(url):
                    urls[url] = (host, "recon")
            # Only main nuclei JSONL; severity bucket copies must not duplicate findings.
            for line in list(lines(root / "nuclei" / "findings.jsonl")) + canonical.nuclei_findings:
                try:
                    row = json.loads(line)
                    info = row.get("info") or {}
                    target = row.get("matched-at") or row.get("host") or row.get("url")
                    host = asset(target)
                    if not host:
                        continue
                    severity = str(info.get("severity", "info")).lower()
                    severity = severity if severity in SEVERITIES else "info"
                    name = str(row.get("template-id") or info.get("name") or "nuclei")
                    findings.append((host, "nuclei", severity, name, {"matched_at": target, "name": info.get("name")}))
                except (ValueError, TypeError, AttributeError):
                    continue
        observed = len(assets) + len(urls) + len(findings)
        with self.database.connect() as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            ids = {}
            for host, row in assets.items():
                conn.execute("INSERT INTO asset(program_id,host,ip,status_code,title,tech_json,category,first_seen_scan,last_seen_scan,state) VALUES(?,?,?,?,?,?,?,?,?,'active') ON CONFLICT(program_id,host) DO UPDATE SET ip=COALESCE(excluded.ip,asset.ip),status_code=COALESCE(excluded.status_code,asset.status_code),title=COALESCE(excluded.title,asset.title),tech_json=COALESCE(excluded.tech_json,asset.tech_json),category=excluded.category,last_seen_scan=excluded.last_seen_scan,state='active'", (
                    plan.program_id, host, row.get("ip"), row.get("status_code"), row.get("title"),
                    json.dumps(row["tech"]) if "tech" in row else None, row["category"], plan.scan_id, plan.scan_id))
                ids[host] = conn.execute("SELECT id FROM asset WHERE program_id=? AND host=?", (plan.program_id, host)).fetchone()[0]
            for url, (host, source) in urls.items():
                conn.execute("INSERT INTO url(program_id,asset_id,url,source,first_seen_scan,last_seen_scan) VALUES(?,?,?,?,?,?) ON CONFLICT(program_id,url) DO UPDATE SET last_seen_scan=excluded.last_seen_scan,asset_id=excluded.asset_id", (
                    plan.program_id, ids[host], url, source, plan.scan_id, plan.scan_id))
            for host, kind, severity, name, details in findings:
                conn.execute("INSERT INTO finding(program_id,asset_id,type,severity,name,detail_json,first_seen_scan,last_seen_scan) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(program_id,type,name,asset_id) DO UPDATE SET severity=excluded.severity,detail_json=excluded.detail_json,last_seen_scan=excluded.last_seen_scan", (
                    plan.program_id, ids[host], kind, severity, name, json.dumps(details), plan.scan_id, plan.scan_id))
        return {"observed": observed, "subs": len(assets), "live": sum("status_code" in row for row in assets.values()),
                "urls": len(urls), "findings": len({(item[0], item[1], item[3]) for item in findings}),
                "observations": assets}
