"""Idempotent ingestion of scoped framework output, including partial scans."""

from collections import Counter
import ipaddress
import json
import re
from urllib.parse import urlsplit

from backend.asm.urlintel import classify_url, url_shape
from backend.framework import load_module
from backend.scope_gate import normalize_host

SEVERITIES = {"info", "low", "medium", "high", "critical"}


def lines(path):
    if path.is_file():
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if line.strip():
                    yield line.strip()


def _in_network(host, network):
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.version == network.version and address in network


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


EVIDENCE = ("status_code", "title", "tech", "ip", "http_live")


class Ingester:
    def __init__(self, settings, database):
        self.settings, self.database = settings, database

    @staticmethod
    def _collapse_ranges(plan, assets, urls, findings):
        """A CIDR is one range asset; individual IPs only exist with real evidence.

        recon_engine enumerates every address of a CIDR into subdomains/all.txt. Treating
        each as an asset made a /24 look like 254 new assets (and a /16 like 65k) even when
        nothing answered. Dead/unprobed addresses are dropped, answering ones are kept.
        """
        exact = set()
        ranges = []
        for pattern in plan.gate.allow:
            if pattern.startswith("repo:"):
                continue
            try:
                if "/" in pattern:
                    ranges.append(ipaddress.ip_network(pattern))
                else:
                    exact.add(str(ipaddress.ip_address(pattern)))
            except ValueError:
                continue
        referenced = {host for host, _ in urls.values()} | {item[0] for item in findings}
        collapsed = 0
        for host in list(assets):
            row = assets[host]
            if row["category"] != "ip" or host in exact or host in referenced:
                continue
            if not any(key in row for key in EVIDENCE):
                del assets[host]
                collapsed += 1
        for network in ranges:
            members = [h for h, r in assets.items() if r["category"] == "ip" and _in_network(h, network)]
            title = f"{network.num_addresses} địa chỉ" + (f" · {len(members)} có phản hồi" if members else "")
            assets[str(network)] = {"category": "cidr", "title": title}
        return collapsed

    def ingest(self, plan):
        module = load_module(self.settings, "recon_adapter.py")
        assets, urls, findings = {}, {}, []
        funnel = {"raw": 0, "in_scope": 0, "out_of_scope": 0, "invalid": 0}
        outside = Counter()
        observed_urls, source_of = set(), {}

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
                if host := asset(url, http_live=True):
                    urls[url] = (host, "httpx")
            for line in lines(root / "live" / "httpx_full.txt"):
                try:
                    url, status, title, tech, ip = httpx_record(line)
                    asset(url, status_code=status, title=title, tech=tech, ip=ip)
                except (ValueError, TypeError, IndexError):
                    continue
            # The pinned engine supplies subdomains/all.txt directly to httpx,
            # then creates live/urls.txt. Missing files or skipped probing are
            # not negative evidence. Diff additionally requires a complete scan.
            if (plan.config.depth != "passive" and command.env.get("BBASM_SKIP_HTTPX") == "0"
                    and (root / "live" / "httpx_full.txt").is_file()
                    and (root / "live" / "urls.txt").is_file()):
                for resource in lines(root / "subdomains" / "all.txt"):
                    asset(resource, http_probed=True)
            # Which tool produced a URL decides how much it proves: crawled by katana = observed on a
            # live host; archive/history sources only say "this URL existed once".
            for filename, label in (("gau.txt", "gau"), ("wayback.txt", "wayback"), ("katana.txt", "katana")):
                for line in lines(root / "urls" / filename):
                    if label == "katana":
                        source_of[line] = label  # crawled on a live host: stronger evidence than any archive
                        observed_urls.add(line)
                    else:
                        source_of.setdefault(line, label)
            for url in set(canonical.urls + nested.get_urls()):
                funnel["raw"] += 1
                if host := asset(url):
                    funnel["in_scope"] += 1
                    urls[url] = (host, source_of.get(url, "recon"))
                    continue
                try:
                    outside[normalize_host(url)] += 1
                    funnel["out_of_scope"] += 1
                except (ValueError, UnicodeError):
                    funnel["invalid"] += 1
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
        by_tag, by_verification = Counter(), Counter()
        url_meta = {}
        for url, (host, source) in urls.items():
            tags, score = classify_url(url)
            verification = "observed" if url in observed_urls else "historical"
            url_meta[url] = (tags, score, verification, url_shape(url))
            by_tag.update(tags)
            by_verification[verification] += 1
        funnel.update(by_tag=dict(by_tag), by_verification=dict(by_verification),
                      out_of_scope_hosts=[{"host": h, "count": c} for h, c in outside.most_common(10)])
        collapsed = self._collapse_ranges(plan, assets, urls, findings)
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
                tags, score, verification, shape = url_meta[url]
                conn.execute("INSERT INTO url(program_id,asset_id,url,source,first_seen_scan,last_seen_scan,tags_json,score,verification,shape) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(program_id,url) DO UPDATE SET last_seen_scan=excluded.last_seen_scan,asset_id=excluded.asset_id,source=excluded.source,tags_json=excluded.tags_json,score=excluded.score,verification=excluded.verification,shape=excluded.shape", (
                    plan.program_id, ids[host], url, source, plan.scan_id, plan.scan_id, json.dumps(tags), score, verification, shape))
            for host, kind, severity, name, details in findings:
                conn.execute("INSERT INTO finding(program_id,asset_id,type,severity,name,detail_json,first_seen_scan,last_seen_scan) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(program_id,type,name,asset_id) DO UPDATE SET severity=excluded.severity,detail_json=excluded.detail_json,last_seen_scan=excluded.last_seen_scan", (
                    plan.program_id, ids[host], kind, severity, name, json.dumps(details), plan.scan_id, plan.scan_id))
        return {"observed": observed, "collapsed_ips": collapsed, "subs": len(assets), "live": sum("status_code" in row for row in assets.values()),
                "urls": len(urls), "url_funnel": funnel, "findings": len({(item[0], item[1], item[3]) for item in findings}),
                "observations": assets}
