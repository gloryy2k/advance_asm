"""What subjack's output actually says. One parser for the scan, the Run page and the repair of older data.

subjack prints one line per checked host: `[Not Vulnerable] host` for a host with nothing wrong and `[SERVICE] host`
(`[GITHUB]`, `[GEMFURY]`…) for a possible takeover. Only the second kind is a candidate, and even that is unverified."""
import re

CLEAN_TAGS = {"not vulnerable", "not_vulnerable", "notvulnerable", "safe", "ok", "clean"}
_LINE = re.compile(r"^\s*\[([^\]]{1,60})\]\s*(\S+)")
_HOST = re.compile(r"^(?:[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?\.)+[a-z0-9-]{2,}$", re.I)


def parse_subjack(lines):
    """-> (candidates [(host, service)], not_vulnerable count, unreadable count). Unbracketed lines are not guessed at."""
    candidates, clean, unreadable = [], 0, 0
    for line in lines:
        if not line.strip():
            continue
        match = _LINE.match(line)
        if not match:
            unreadable += 1
            continue
        tag, host = match.group(1).strip(), match.group(2).strip().rstrip(".")
        if tag.lower() in CLEAN_TAGS:
            clean += 1
        elif _HOST.match(host):
            candidates.append((host, tag.upper()))
        else:
            unreadable += 1
    return candidates, clean, unreadable


def summarize(path):
    from backend.jobs.ingest import lines
    candidates, clean, unreadable = parse_subjack(lines(path))
    return {"candidates": len({h for h, _ in candidates}), "not_vulnerable": clean, "unreadable": unreadable}
