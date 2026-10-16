"""URL inventory as a sitemap tree (host -> folders -> files), one level at a time so 100k URLs never reach the browser at once."""
from collections import defaultdict
from urllib.parse import unquote, urlsplit
import json

MAX_ROWS = 200_000          # rows read per request; more than this is reported as `truncated`
MAX_NODES = 3000            # nodes returned by one request (depth > 1)
TAG_ORDER = ("admin", "auth", "api", "sensitive", "redirect-param", "id-param", "file-param", "upload", "docs", "js", "params")


def parse_rows(rows):
    """[(netloc, [raw segments], query, row)] for every stored URL; unparseable URLs are skipped."""
    parsed = []
    for row in rows:
        try:
            parts = urlsplit(row["url"])
            host = parts.hostname
            if not host:
                continue
            netloc = host + (f":{parts.port}" if parts.port else "")
        except ValueError:
            continue
        segments = [s for s in parts.path.split("/") if s]
        parsed.append((netloc.lower(), segments, parts.query, row))
    return parsed


def _summary(entries, depth_index, latest):
    """Aggregate one group of entries that share the same prefix of length depth_index+1."""
    exact = [e for e in entries if len(e[1]) == depth_index + 1]
    tags = defaultdict(int)
    verified = "historical"
    best = None
    for _, _, _, row in entries:
        for tag in json.loads(row["tags_json"] or "[]"):
            tags[tag] += 1
        if row["verification"] in ("observed", "live"):
            verified = "observed"
    for entry in exact:
        if best is None or (entry[3]["score"] or 0) > (best[3]["score"] or 0):
            best = entry
    firsts = [e[3]["first_seen_scan"] for e in entries if e[3]["first_seen_scan"] is not None]
    lasts = [e[3]["last_seen_scan"] for e in entries if e[3]["last_seen_scan"] is not None]
    return {
        "count": len(entries),
        "self_count": len(exact),
        "variants": len({e[2] for e in exact if e[2]}),
        "has_children": any(len(e[1]) > depth_index + 1 for e in entries),
        "max_score": max((e[3]["score"] or 0 for e in entries), default=0),
        "tags": [t for t in TAG_ORDER if t in tags][:4],
        "verification": verified,
        "is_new": bool(latest) and any(e[3]["first_seen_scan"] == latest for e in entries),
        "first_seen_scan": min(firsts) if firsts else None,
        "last_seen_scan": max(lasts) if lasts else None,
        "url": best[3]["url"] if best else None,
    }


def _order(nodes, sort, folders_first):
    def key(node):
        name = node["display"].lower()
        if sort == "score":
            primary = (-node["max_score"], name)
        elif sort == "count":
            primary = (-node["count"], name)
        else:
            primary = (name,)
        return ((0 if node["has_children"] else 1,) if folders_first else ()) + primary
    return sorted(nodes, key=key)


class Budget:
    def __init__(self, nodes):
        self.left, self.truncated = nodes, False

    def take(self):
        if self.left <= 0:
            self.truncated = True
            return False
        self.left -= 1
        return True


def build_level(parsed, host, prefix, *, depth, sort, folders_first, limit, offset, latest, budget):
    """Children of `prefix` (list of raw segments) under `host` (None = the host list)."""
    groups = defaultdict(list)
    if host is None:
        for entry in parsed:
            groups[entry[0]].append(entry)
        index = -1
    else:
        index = len(prefix)
        for entry in parsed:
            if entry[0] == host and entry[1][:index] == prefix and len(entry[1]) > index:
                groups[entry[1][index]].append(entry)
    nodes = []
    for name, entries in groups.items():
        info = _summary(entries, index if host is not None else -1, latest)
        if host is None:
            info["self_count"] = sum(1 for e in entries if not e[1])
            info["has_children"] = any(e[1] for e in entries)
            info["url"] = next((e[3]["url"] for e in entries if not e[1]), None)
        path = "/" + "/".join(prefix + ([name] if host is not None else []))
        nodes.append({"name": name, "display": unquote(name) if host is not None else name,
                      "kind": "host" if host is None else ("dir" if info["has_children"] else "file"),
                      "host": name if host is None else host, "path": "/" if host is None else path,
                      "entries": entries, **info})
    ordered = _order(nodes, sort, folders_first)
    total = len(ordered)
    page = ordered[offset:offset + limit]
    result = []
    for node in page:
        if not budget.take():
            break
        entries = node.pop("entries")
        node["children"] = None
        if depth > 1 and node["has_children"]:
            sub_prefix = prefix if host is None else prefix + [node["name"]]
            sub_host = node["name"] if host is None else host
            sub = build_level([e for e in entries], sub_host, sub_prefix, depth=depth - 1, sort=sort,
                              folders_first=folders_first, limit=limit, offset=0, latest=latest, budget=budget)
            node["children"], node["children_total"] = sub
        result.append(node)
    return result, total
