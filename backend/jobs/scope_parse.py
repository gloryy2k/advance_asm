"""Tolerant, fail-closed parsing of pasted raw scope; shared by preview and resolve.

Never guess when the intent is ambiguous: a line that looks like an OUT header but is
not exactly one, a non-strict CIDR, or an unsupported wildcard is an *error*, never
silently classified (a wrongly-IN host is scanned; a wrongly-OUT host is merely skipped).
"""

from dataclasses import dataclass, field
import ipaddress
import re
from urllib.parse import urlsplit

from backend.jobs.scope_resolver import ScopeError, classify
from backend.models import ScopeEntry

MAX_RANGE_CIDRS = 32
# A header needs "#" or a trailing colon, so a bare word is never mistaken for one.
_IN_HEADER = re.compile(r"^(?:#\s*(?:in|in[- ]scope)\s*:?|(?:in|in[- ]scope)\s*:)\s*$", re.I)
_OUT_HEADER = re.compile(r"^(?:#\s*(?:out|oos|out[- ]of[- ]scope|exclude[ds]?)\s*:?|(?:out|oos|out[- ]of[- ]scope|exclude[ds]?)\s*:)\s*$", re.I)
_LOOKS_LIKE_OUT = re.compile(r"^#\s*(?:out|oos|exclude)", re.I)
_BULLET = re.compile(r"^(?:[-*+•]\s+|\d+[.)]\s+)")
_INLINE_COMMENT = re.compile(r"\s+#.*$")
_SPLIT = re.compile(r"[,;\s]+")
_IPV4_RANGE = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})-(\d{1,3}(?:\.\d{1,3}){3}|\d{1,3})$")
_APP_ID_HINT = re.compile(r"^(?:com|org|net|io|app)\.[a-z0-9_]+\.[a-z0-9_.]+$", re.I)


@dataclass
class LineResult:
    box: str            # "in" | "out": which input box the line came from
    line: int           # 1-based line number within that box
    raw: str
    status: str         # ok | warn | error | skip
    kind: str = "in"
    category: str = ""
    normalized: str = ""
    note: str = ""
    entry: ScopeEntry | None = field(default=None, repr=False)
    shadowed_by: str = ""   # the OUT rule that cancels this IN line (OUT always wins)

    def public(self) -> dict:
        return {"box": self.box, "line": self.line, "raw": self.raw, "status": self.status,
                "kind": self.kind, "category": self.category,
                "normalized": self.normalized, "note": self.note, "shadowed_by": self.shadowed_by}


def _expand_range(token: str):
    match = _IPV4_RANGE.match(token)
    if not match:
        return None
    start = ipaddress.IPv4Address(match.group(1))
    tail = match.group(2)
    end = ipaddress.IPv4Address(tail) if "." in tail else ipaddress.IPv4Address(
        ".".join([*match.group(1).split(".")[:3], tail]))
    if end < start:
        raise ValueError("range end is before start")
    networks = list(ipaddress.summarize_address_range(start, end))
    if len(networks) > MAX_RANGE_CIDRS:
        raise ValueError(f"range expands to {len(networks)} CIDR blocks (max {MAX_RANGE_CIDRS})")
    return [str(n) if n.prefixlen < 32 else str(n.network_address) for n in networks]


def _token(raw, token, kind, box, line, results):
    notes = []
    value = token.strip("\"'`()[]<>")
    if not value:
        return
    lowered = value.lower()
    try:
        expanded = _expand_range(value)
        if expanded is not None:
            notes.append(f"Dải IP → {len(expanded)} CIDR")
            for item in expanded:
                entry = classify(item, kind)
                results.append(LineResult(box, line, raw, "warn", kind, entry.category,
                                          entry.pattern, "; ".join(notes), entry))
            return
        if lowered.startswith(("http://*.", "https://*.")):
            value = value.split("://", 1)[1]
            notes.append("Bỏ scheme khỏi wildcard")
        if "*" in value and not value.startswith("*."):
            raise ScopeError("Wildcard chỉ hỗ trợ ở đầu dạng *.domain")
        if re.fullmatch(r"(?:https?://)?(?:github\.com|gitlab\.com|bitbucket\.org)/[^\s?#]+", value, re.I):
            value = "repo:" + (value if "://" in value else "https://" + value)
            notes.append("Tự thêm repo: cho kho mã")
        elif "/" in value and "://" not in value and not value.lower().startswith(("repo:", "app:")):
            try:
                network = ipaddress.ip_network(value, strict=False)
            except ValueError:
                raise ScopeError("Không nhận diện được; CIDR phải dạng 10.0.0.0/24") from None
            if str(network) != value:
                raise ScopeError(f"CIDR không chuẩn; ý bạn là {network}?")
        elif "://" not in value and not value.startswith(("*.", "repo:", "app:")):
            host, _, port = value.rpartition(":")
            if host and port.isdigit() and ":" not in host:
                value = host
                notes.append(f"Bỏ port {port}; scope áp theo host")
        if "://" in value and not value.lower().startswith("repo:"):
            path = urlsplit(value).path
            if path not in ("", "/"):
                notes.append("OUT theo đường dẫn: chỉ chặn đường dẫn này; host đó chỉ được probe, không crawl/nuclei (trừ khi bạn bật ở Review)"
                             if kind == "out" else "URL có đường dẫn: recon vẫn chạy trên cả host")
        if not re.search(r"[./:*]", value) and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
            raise ScopeError("Ký tự không hợp lệ trong scope")
        entry = classify(value, kind)
        if entry.category == "other" and not value.lower().startswith("app:"):
            notes.append("Không nhận diện được loại; sẽ làm thủ công, không auto-recon")
        elif entry.category == "web" and _APP_ID_HINT.match(entry.pattern):
            notes.append("Trông giống app id; nếu là mobile hãy viết app:" + entry.pattern)
        elif entry.category == "mobile":
            notes.append("Mobile: làm thủ công, không auto-recon")
        status = "warn" if notes else "ok"
        results.append(LineResult(box, line, raw, status, kind, entry.category, entry.pattern,
                                  "; ".join(notes), entry))
    except (ScopeError, ValueError) as exc:
        message = str(exc)
        if message.startswith("Invalid scope entry"):
            message = "Không hợp lệ (domain, IP, CIDR, *.domain, repo:, app:)"
        results.append(LineResult(box, line, raw, "error", kind, "", value, message))


def parse_box(lines, box="in", default_kind=None):
    """Parse one input box. The legacy single-box form may switch kind with headers."""
    kind = default_kind or "in"
    results = []
    for number, raw in enumerate(lines, 1):
        text = raw.replace("\r", "").strip()
        if not text:
            continue
        if _OUT_HEADER.match(text) or _IN_HEADER.match(text):
            header = "out" if _OUT_HEADER.match(text) else "in"
            if default_kind is not None and header != default_kind:
                results.append(LineResult(box, number, raw, "error", default_kind, "", "",
                                          f"Header {header.upper()} nằm trong ô {default_kind.upper()}"))
            else:
                kind = header
                results.append(LineResult(box, number, raw, "skip", kind, note=f"Các dòng sau là {kind.upper()}"))
            continue
        if text.startswith("#"):
            if _LOOKS_LIKE_OUT.match(text):
                results.append(LineResult(box, number, raw, "error", kind, "", "",
                                          "Giống header OUT nhưng sai cú pháp; dùng đúng '# OUT' hoặc nhập ở ô OUT"))
            else:
                results.append(LineResult(box, number, raw, "skip", kind, note="Ghi chú, bỏ qua"))
            continue
        text = _BULLET.sub("", _INLINE_COMMENT.sub("", text)).strip()
        line_results = []
        for token in _SPLIT.split(text):
            if token:
                _token(raw, token, kind, box, number, line_results)
        if any(r.status == "error" for r in line_results):
            # "bad host!!" is one broken line, not a valid word "bad" plus an error: show only the error.
            line_results = [r for r in line_results if r.status == "error"]
        results.extend(line_results)
    return results


def _network(value):
    try:
        return ipaddress.ip_network(value, strict=False)
    except ValueError:
        return None


def _covers(out_pattern, in_pattern):
    """True when the OUT rule removes the whole IN rule. Partial overlaps stay with ScopeGate at scan time."""
    if out_pattern == in_pattern:
        return True
    out_net, in_net = _network(out_pattern), _network(in_pattern)
    if out_net is not None or in_net is not None:
        return bool(out_net and in_net and out_net.version == in_net.version and in_net.subnet_of(out_net))
    if out_pattern.startswith("*."):
        return in_pattern.removeprefix("*.").endswith("." + out_pattern[2:])
    return False


def apply_precedence(results):
    """OUT beats IN. Show that in the preview instead of listing an excluded host as scannable."""
    outs = [r.entry.pattern for r in results if r.entry is not None and r.kind == "out"]
    for r in results:
        if r.entry is None or r.kind != "in":
            continue
        rule = next((o for o in outs if _covers(o, r.entry.pattern)), None)
        if rule:
            r.shadowed_by = rule
            r.status = "warn" if r.status == "ok" else r.status
            r.note = (r.note + "; " if r.note else "") + f"Bị OUT '{rule}' loại: OUT luôn thắng IN, mục này sẽ không được quét"
    return results


def parse_scope(scope_in, scope_out=()):
    """IN box (may contain legacy headers) + dedicated OUT box -> ordered line results."""
    results = parse_box(scope_in, "in")
    results += parse_box(scope_out, "out", default_kind="out")
    return apply_precedence(results)


def summarize(results):
    entries = [r for r in results if r.entry is not None]
    return {"in": sum(1 for r in entries if r.kind == "in"), "out": sum(1 for r in entries if r.kind == "out"),
            "effective_in": sum(1 for r in entries if r.kind == "in" and not r.shadowed_by),
            "errors": sum(1 for r in results if r.status == "error"),
            "warnings": sum(1 for r in results if r.status == "warn")}


def entries_or_raise(results):
    errors = [r for r in results if r.status == "error"]
    if errors:
        detail = "; ".join(f"ô {r.box.upper()} dòng {r.line}: {r.note} ({r.raw.strip()[:60]})" for r in errors[:5])
        extra = f" (+{len(errors) - 5} lỗi nữa)" if len(errors) > 5 else ""
        raise ScopeError(f"Scope có {len(errors)} dòng lỗi — {detail}{extra}", "scope_invalid")
    if any(r.kind == "in" and r.entry is not None for r in results) and not any(
            r.kind == "in" and r.entry is not None and not r.shadowed_by for r in results):
        raise ScopeError("Mọi mục IN đều nằm trong OUT nên không còn gì để quét. OUT luôn thắng IN; kiểm lại hai ô.", "scope_empty_after_out")
    unique = {}
    for r in results:
        if r.entry is not None:
            unique[(r.entry.pattern, r.entry.kind)] = r.entry
    warnings = [f"{r.box.upper()}:{r.line} {r.note}" for r in results if r.status == "warn" and r.note]
    return list(unique.values()), list(dict.fromkeys(warnings))
