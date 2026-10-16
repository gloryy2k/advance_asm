"""Structured, honest readings of what nmap and ffuf wrote. They only read files; nothing here touches a target.

Why this exists (arc-bbp Strong #65): the Run page counted LINES of a file instead of results, took an nmap file that stopped
mid-scan for a finished one, listed only the last port of each host, and showed 24 identical 403 block pages as 24 "paths"."""
import ipaddress
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

# Cloudflare's published IPv4 ranges (a static copy: it can go stale, so a CDN verdict from here says "likely", and the
# service banner is read as well). Other CDNs are recognised from nmap's service text only.
CLOUDFLARE_V4 = [ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
    "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22")]
CDN_BANNERS = {"cloudflare": "Cloudflare", "akamai": "Akamai", "cloudfront": "Amazon CloudFront", "fastly": "Fastly",
               "incapsula": "Imperva", "sucuri": "Sucuri", "azure front": "Azure Front Door"}

_PORT = re.compile(r"(\d+)/([a-z|]+)/(tcp|udp|sctp)//([^/]*)/[^/]*/([^/]*)/?")
_HOST = re.compile(r"^Host:\s+(\S+)\s+\(([^)]*)\)")


def cdn_of(ip, banners=()):
    """-> a CDN/shared-edge name or None. `banners` are the service/version strings nmap printed for that host."""
    text = " ".join(banners).lower()
    for needle, name in CDN_BANNERS.items():
        if needle in text:
            return name
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if address.version == 4 and any(address in net for net in CLOUDFLARE_V4):
        return "Cloudflare"
    return None


def read_nmap_greppable(path):
    """Every host/port/protocol pair. `complete` is True only when nmap wrote its closing "# Nmap done" line."""
    pairs, hosts, complete, reported = [], {}, False, 0
    try:
        stream = Path(path).open(encoding="utf-8", errors="replace")
    except OSError:
        return {"pairs": [], "hosts": 0, "reported": 0, "complete": False, "exists": False}
    with stream:
        for line in stream:
            if line.startswith("# Nmap done"):
                complete = True
                continue
            match = _HOST.match(line)
            if not match or "Ports:" not in line:
                if match:
                    reported += 1
                continue
            reported += 1
            ip, name = match.group(1), match.group(2) or match.group(1)
            for port, state, proto, service, version in _PORT.findall(line.split("Ports:", 1)[1]):
                if state.split("|")[0] != "open":
                    continue
                pairs.append({"host": name, "ip": ip, "port": int(port), "proto": proto, "service": service, "version": version.strip()})
                hosts.setdefault(name, ip)
    return {"pairs": pairs, "hosts": len(hosts), "reported": reported, "complete": complete, "exists": True}


def summarize_ports(root):
    """All nmap runs of one scan folder, merged. Pairs are kept per host: two hosts sharing a port are two observations."""
    pairs, files, all_complete, any_file = [], [], True, False
    for path in sorted(Path(root).glob("*/ports/nmap_greppable.txt")):
        if path.is_symlink():
            continue
        any_file = True
        part = read_nmap_greppable(path)
        files.append({"file": path.relative_to(root).as_posix(), "pairs": len(part["pairs"]), "hosts": part["hosts"], "complete": part["complete"]})
        all_complete = all_complete and part["complete"]
        pairs.extend(part["pairs"])
    unique = {(p["port"], p["proto"]) for p in pairs}
    banners = defaultdict(list)
    for p in pairs:
        banners[p["ip"]].append(f'{p["service"]} {p["version"]}')
    edge = {}
    for ip, texts in banners.items():
        name = cdn_of(ip, texts)
        if name:
            edge[ip] = name
    hosts = {p["host"] for p in pairs}
    return {"found": any_file, "pairs": len(pairs), "hosts": len(hosts), "unique_ports": len(unique), "complete": any_file and all_complete,
            "files": files, "rows": pairs[:500], "cdn": sorted(set(edge.values())), "cdn_hosts": sorted({p["host"] for p in pairs if p["ip"] in edge}),
            "cdn_pairs": sum(1 for p in pairs if p["ip"] in edge)}


def read_ffuf(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    results = [r for r in data.get("results") or [] if isinstance(r, dict)]
    signature = Counter((r.get("status"), r.get("length"), r.get("words")) for r in results)
    noisy = {sig for sig, n in signature.items() if n >= 5 and n / max(1, len(results)) >= 0.6}
    host = ""
    if results:
        host = str(results[0].get("host") or "")
    if not host:
        match = re.search(r"https?://([^/\s]+)", str(data.get("commandline") or ""))
        host = match.group(1) if match else Path(path).stem.removeprefix("ffuf_")
    significant = [r for r in results if (r.get("status"), r.get("length"), r.get("words")) not in noisy]
    by_status = Counter(r.get("status") for r in significant)
    return {"host": host, "total": len(results), "noise": len(results) - len(significant),
            "noise_signature": [{"status": s, "length": l, "words": w, "count": signature[(s, l, w)]} for s, l, w in noisy],
            "significant": [{"url": r.get("url"), "status": r.get("status"), "length": r.get("length")} for r in significant][:200],
            "by_status": {str(k): v for k, v in by_status.items()}, "calibrated": bool((data.get("config") or {}).get("autocalibration"))}


def summarize_dirs(root):
    hosts = []
    for path in sorted(Path(root).glob("*/dirs/ffuf_*.json")):
        if path.is_symlink():
            continue
        item = read_ffuf(path)
        if item is not None:
            hosts.append({**item, "file": path.relative_to(root).as_posix()})
    total = sum(h["total"] for h in hosts)
    noise = sum(h["noise"] for h in hosts)
    return {"found": bool(hosts), "hosts": hosts, "total": total, "noise": noise, "significant": total - noise,
            "blocked_only": [h["host"] for h in hosts if h["total"] and set(h["by_status"]) <= {"403"}]}
