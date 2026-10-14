"""Audited metadata transport and offline adapter for the pinned aggregator."""

import json
import os
import re
from pathlib import Path
import subprocess
import tempfile

import httpx

from backend.db import utc_now
from backend.jobs.scope_resolver import ScopeError, classify
from backend.scope_gate import ScopeGate, audit

DUMP_URL = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/hackerone_data.json"
API_BASE = "https://api.hackerone.com/v1/hackers/programs"
PAGE_GRAPHQL_URL = "https://hackerone.com/graphql"
MAX_METADATA_BYTES = 50 * 1024 * 1024
MAX_PAGE_BYTES = 5 * 1024 * 1024   # a public program page is text; anything bigger is not what we asked for
MAX_PAGE_REQUESTS = 20             # 100 assets per request
# The read-only query the public program page itself issues for policy + structured scope.
# NOTE: written from the documented public schema and covered by mocks only; the field names must be
# confirmed against the live site on a networked host. If they are wrong the provider reports
# "page structure unexpected" and the resolver falls back to the dump, flagged as insufficient.
PAGE_QUERY = """query BbasmPolicyScope($handle: String!, $cursor: String) {
  team(handle: $handle) {
    handle name policy
    structured_scopes(first: 100, after: $cursor, archived: false) {
      pageInfo { hasNextPage endCursor }
      edges { node { asset_type asset_identifier eligible_for_submission eligible_for_bounty instruction max_severity } }
    }
  }
}"""
# Same query plus the page's own totals (the profile page shows them as "assets in scope"); used to prove we read everything.
PAGE_QUERY_COUNTS = PAGE_QUERY.replace("    handle name policy\n", """    handle name policy
    assets_in: structured_scopes_search(eligible_for_submission: true) { total_count }
    assets_out: structured_scopes_search(eligible_for_submission: false) { total_count }
""")
# The public GraphQL endpoint answers browser-like clients; a bare library user agent may be refused.
PAGE_USER_AGENT = "Mozilla/5.0 (compatible; BBASM-metadata-reader; read-only)"
AUTO_CATEGORIES = {"web", "wildcard", "ip", "cidr"}  # what recon can actually target
# H1 sometimes files a perfectly concrete host under asset_type OTHER. A clean domain/wildcard/IP is still a precise rule.
_CLEAN_HOST = re.compile(r"(?:\*\.)?(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}")
_GLOB_HOST = re.compile(r"[A-Za-z0-9*-]+(?:\.[A-Za-z0-9*-]+)+")


class HackerOneScopeProvider:
    def __init__(self, settings, transport=None, run=None):
        self.settings = settings
        self.transport = transport
        self.run = run or subprocess.run

    def _get(self, client, gate, url, *, method="GET", limit=MAX_METADATA_BYTES, **kwargs):
        if not gate.in_scope(url):
            raise ScopeError("Metadata destination denied", "metadata_denied")
        # No redirects/proxies: a 3xx raises below, so credentials never travel to another origin.
        with client.stream(method, url, **kwargs) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > limit:
                    raise ScopeError("Scope metadata exceeds size limit")
                chunks.append(chunk)
        return json.loads(b"".join(chunks))

    def _public_page(self, client, gate, handle, counts=True):
        """Policy + structured scope of one public program, read without any credential.

        With counts=True the page's own totals are requested too, so a short read is detected instead of trusted."""
        targets = {"in_scope": [], "out_of_scope": []}
        name, policy, cursor, totals = "", "", None, {}
        for _ in range(MAX_PAGE_REQUESTS):
            data = self._get(client, gate, PAGE_GRAPHQL_URL, method="POST", limit=MAX_PAGE_BYTES,
                             json={"query": PAGE_QUERY_COUNTS if counts else PAGE_QUERY, "variables": {"handle": handle, "cursor": cursor}},
                             headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": PAGE_USER_AGENT})
            if counts and isinstance(data, dict) and data.get("errors"):
                raise ScopeError("Public page refused the totals fields", "public_page_fields")
            team = ((data or {}).get("data") or {}).get("team") if isinstance(data, dict) else None
            if (not isinstance(data, dict) or data.get("errors") or not isinstance(team, dict)
                    or str(team.get("handle", "")).lower() != handle):
                raise ScopeError("Public page structure unexpected", "public_page_unexpected")
            name = team.get("name") if isinstance(team.get("name"), str) else name
            policy = team.get("policy") if isinstance(team.get("policy"), str) else policy
            for key, alias in (("in", "assets_in"), ("out", "assets_out")):
                total = (team.get(alias) or {}).get("total_count") if isinstance(team.get(alias), dict) else None
                if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
                    totals[key] = total
            scopes = team.get("structured_scopes")
            if not isinstance(scopes, dict) or not isinstance(scopes.get("edges"), list):
                raise ScopeError("Public page structure unexpected", "public_page_unexpected")
            for edge in scopes["edges"]:
                node = edge.get("node") if isinstance(edge, dict) else None
                if not isinstance(node, dict) or not isinstance(node.get("asset_identifier"), str) \
                        or not isinstance(node.get("eligible_for_submission"), bool):
                    raise ScopeError("Public page scope item malformed", "public_page_unexpected")
                targets["in_scope" if node["eligible_for_submission"] else "out_of_scope"].append(node)
            info = scopes.get("pageInfo") or {}
            if not info.get("hasNextPage"):
                if not policy.strip() and not targets["in_scope"] and not targets["out_of_scope"]:
                    raise ScopeError("Public page returned neither policy nor scope", "public_page_unexpected")
                fetched = {"in": len(targets["in_scope"]), "out": len(targets["out_of_scope"])}
                counts_info = ({k: {"fetched": fetched[k], "total": totals[k]} for k in ("in", "out")}
                               if set(totals) == {"in", "out"} else None)
                return {"handle": handle, "name": name, "policy": policy, "targets": targets, "_counts": counts_info}
            cursor = info.get("endCursor")
            if not isinstance(cursor, str):
                raise ScopeError("Public page pagination malformed", "public_page_unexpected")
        raise ScopeError("Public page pagination limit exceeded", "public_page_unexpected")

    def _api_program(self, client, gate, handle):
        auth = (self.settings.H1_USER.get_secret_value(), self.settings.H1_TOKEN.get_secret_value())
        program_data = self._get(client, gate, f"{API_BASE}/{handle}", auth=auth)
        attributes = program_data["data"]["attributes"]
        if str(attributes.get("handle", "")).lower() != handle:
            raise ScopeError("Program metadata handle mismatch")
        url = f"{API_BASE}/{handle}/structured_scopes"
        targets = {"in_scope": [], "out_of_scope": []}
        # Fixed URL and integer pagination, never trust arbitrary links.next URLs.
        for page in range(1, 101):
            data = self._get(client, gate, url, auth=auth, params={"page[number]": page, "page[size]": 100})
            if not isinstance(data, dict) or not isinstance(data.get("data"), list):
                raise ScopeError("Malformed structured scope metadata")
            for item in data["data"]:
                scope_attributes = item["attributes"]
                if not isinstance(scope_attributes.get("eligible_for_submission"), bool):
                    raise ScopeError("Missing scope eligibility")
                key = "in_scope" if scope_attributes["eligible_for_submission"] else "out_of_scope"
                targets[key].append(scope_attributes)
            if not data.get("links", {}).get("next"):
                return {**attributes, "handle": handle, "targets": targets}
        raise ScopeError("Scope pagination limit exceeded")

    def _public_program(self, client, gate, handle):
        dump = self._get(client, gate, DUMP_URL)
        if not isinstance(dump, list):
            raise ScopeError("Malformed scope dump")
        matches = [p for p in dump if isinstance(p, dict) and str(p.get("handle", "")).lower() == handle]
        if len(matches) != 1:
            raise ScopeError("No unique exact HackerOne handle in scope metadata", "scope_empty")
        return matches[0]

    @staticmethod
    def _by_shape(identifier, kind, instruction, by_shape):
        """An OTHER-typed identifier that is itself a clean host rule is accepted by its form; anything else is not."""
        text = str(identifier).strip()
        try:
            if _CLEAN_HOST.fullmatch(text):
                entry = classify(text, kind, None, instruction)
            elif kind == "out" and "*" in text and _GLOB_HOST.fullmatch(text):
                entry = classify(text, kind, None, instruction)   # excluding more than written is always safe
            else:
                entry = None
        except ScopeError:
            entry = None
        if entry is not None and entry.category in AUTO_CATEGORIES:
            by_shape.append({"identifier": text[:200], "kind": kind})
            return entry, ""
        return None, "Loại asset không rõ (ví dụ Open Scope/OTHER): không suy diễn thành quyền quét"

    @staticmethod
    def _entries(program, by_shape=None):
        """(entries, unclassified). Only assets we can name precisely reach the scope gate.

        "Open Scope", a bare "*", "*.com" or free text are never widened into "scan anything": they are listed
        as unclassified so the Review page can say what is missing."""
        targets = program.get("targets")
        if not isinstance(targets, dict) or not isinstance(targets.get("in_scope"), list) or not isinstance(targets.get("out_of_scope"), list):
            raise ScopeError("Cannot distinguish IN/OUT scope; refusing unlabelled output")
        result, unclassified = [], []
        by_shape = by_shape if by_shape is not None else []
        for key, kind in (("in_scope", "in"), ("out_of_scope", "out")):
            for asset in targets[key]:
                if isinstance(asset, str):
                    identifier, asset_type, instruction, actual_kind = asset, None, "", kind
                elif isinstance(asset, dict) and isinstance(asset.get("asset_identifier"), str):
                    identifier, asset_type = asset["asset_identifier"], asset.get("asset_type")
                    instruction = asset.get("instruction") or ""
                    # Explicit ineligibility wins over the dump's pool label.
                    actual_kind = "out" if asset.get("eligible_for_submission") is False else kind
                else:
                    raise ScopeError("Malformed scope asset")
                try:
                    entry = classify(identifier, actual_kind, asset_type, instruction)
                except ScopeError:
                    entry, reason = None, "Định dạng không nhận diện được"
                else:
                    reason = ""
                    if entry.category == "other":
                        entry, reason = HackerOneScopeProvider._by_shape(identifier, actual_kind, instruction, by_shape)
                    elif entry.category == "wildcard" and "." not in entry.pattern[2:]:
                        entry, reason = None, "Wildcard quá rộng (không có domain cụ thể)"
                if entry is None:
                    text = str(identifier).strip()
                    describes = bool(re.search(r"\s", text)) or not re.search(r"[.*/:]", text)
                    # A description ("Other", "Fraud Reports") names no host, so it cannot hide an IN host from the gate.
                    blocking = actual_kind == "out" and not describes
                    if describes and not reason.startswith("Wildcard"):
                        reason = "Mô tả, không phải host cụ thể: không thi hành được ở scope gate; hãy tự đọc policy"
                    unclassified.append({"identifier": text[:200], "kind": actual_kind, "blocking": blocking,
                                         "asset_type": str(asset_type or "")[:40], "reason": reason})
                else:
                    result.append(entry)
        return result, unclassified

    @staticmethod
    def _reason(exc):
        """A short, credential-free explanation of why a source failed."""
        if isinstance(exc, ScopeError):
            return str(exc)[:120]
        if isinstance(exc, httpx.HTTPStatusError):
            return f"HTTP {exc.response.status_code}"
        if isinstance(exc, httpx.HTTPError):
            return "Lỗi mạng hoặc quá thời gian"
        return "Dữ liệu trả về không đúng cấu trúc"

    def resolve(self, handle: str, audit_path: Path):
        script = self.settings.tool_path("scope_aggregator.sh")
        if not script.is_file() or not self.settings.tool_path("scope_checker.py").is_file():
            raise ScopeError("Framework missing: run git submodule update --init", "framework_missing")
        gate = ScopeGate(["raw.githubusercontent.com", "api.hackerone.com", "hackerone.com"], [], audit_path, self.settings)
        warnings, attempts = [], []
        try:
            with httpx.Client(transport=self.transport, timeout=20, follow_redirects=False, trust_env=False) as client:
                program, source = None, "public_dump"
                has_token = bool(self.settings.H1_TOKEN.get_secret_value() and self.settings.H1_USER.get_secret_value())
                if has_token:
                    try:
                        program = self._api_program(client, gate, handle)
                        source = "api"
                        attempts.append({"source": "api", "ok": True})
                    except (httpx.HTTPError, ScopeError, ValueError, KeyError, TypeError) as exc:
                        attempts.append({"source": "api", "ok": False, "reason": self._reason(exc)})
                        warnings.append("HackerOne API unavailable; trying the public page")
                else:
                    attempts.append({"source": "api", "ok": False, "reason": "Chưa cấu hình H1_USER/H1_TOKEN"})
                if program is None:
                    try:
                        try:
                            program = self._public_page(client, gate, handle)
                        except ScopeError as refused:
                            if getattr(refused, "code", "") != "public_page_fields":
                                raise
                            # The totals fields were refused (schema drift): retry the plain query once.
                            program = self._public_page(client, gate, handle, counts=False)
                        source = "public_page"
                        attempts.append({"source": "public_page", "ok": True})
                    except (httpx.HTTPError, ScopeError, ValueError, KeyError, TypeError) as exc:
                        attempts.append({"source": "public_page", "ok": False, "reason": self._reason(exc)})
                        warnings.append("Không đọc được trang công khai HackerOne; dùng bản sao bounty-targets-data (có thể cũ, không có policy)")
                if program is None:
                    program = self._public_program(client, gate, handle)
                    attempts.append({"source": "public_dump", "ok": True})
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, ScopeError):
                raise
            # Do not expose tokens or remote response bodies in API errors.
            raise ScopeError("Scope metadata unavailable", "metadata_unavailable") from None
        completeness = program.pop("_counts", None)
        by_shape = []
        entries, unclassified = self._entries(program, by_shape)
        self.settings.BBASM_DATA.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="scope-", dir=self.settings.BBASM_DATA) as directory:
            directory = Path(directory)
            cache = directory / "hackerone.json"
            cache.write_text(json.dumps([program]), encoding="utf-8")
            output = directory / "scope.txt"
            # Read pinned scope_aggregator.sh: curl and bbscope are its only transports.
            # Source the original script in bash with local transport functions disabled.
            # No shell interpolation of user input. Fresh isolated cache has the exact program.
            command = ["bash", "--noprofile", "--norc", "-c",
                       'bbscope() { return 1; }; curl() { return 1; }; source "$0" "$@"',
                       str(script.resolve()), handle, "--platform", "h1",
                       "--include-oos", "--out", str(output)]
            env = {key: value for key, value in os.environ.items() if key in {
                "PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL",
            }}
            env.update(HOME=str(directory), BBHUNT_CACHE_DIR=str(directory))
            audit(audit_path, handle, "offline", "scope_aggregator", transport="disabled")
            try:
                completed = self.run(command, env=env, capture_output=True, text=True, timeout=30, check=False)
            except (OSError, subprocess.TimeoutExpired):
                raise ScopeError("Scope aggregator unavailable or timed out", "aggregator_failed") from None
            if completed.returncode not in (0, 1):
                raise ScopeError("Scope aggregator failed", "aggregator_failed")
            # Code 1 can mean no web assets: mobile/source/IP scopes still must resolve.
            # Never treat flattened output as an allowlist: it lost eligibility/type data.
            if completed.returncode == 1:
                warnings.append("Aggregator produced no web host list; structured metadata retained")
        policy_text = program.get("policy") if isinstance(program.get("policy"), str) else ""
        policy_text = policy_text.strip()
        if source == "public_dump":
            warnings.append("Dữ liệu từ nguồn công khai (bounty-targets-data): có thể đã cũ và không có policy đầy đủ. "
                            "Đọc policy chính thức trên HackerOne trước khi chạy.")
        elif source == "public_page":
            warnings.append("Dữ liệu đọc từ trang công khai HackerOne, chưa xác minh bằng API: đối chiếu với trang chính thức.")
        if not policy_text:
            warnings.append("Chưa có nội dung policy; dán policy/hướng dẫn của program khi nhập hoặc bổ sung ở PROGRAM.md.")
        if by_shape:
            warnings.append(f"{len(by_shape)} asset khai báo loại OTHER nhưng có dạng domain/wildcard rõ ràng nên được nhận theo hình thức: "
                            + ", ".join(f"{b['identifier'][:40]} ({b['kind'].upper()})" for b in by_shape[:5]) + ("…" if len(by_shape) > 5 else ""))
        if unclassified:
            shown = ", ".join(f"{u['identifier'][:40]} ({u['kind'].upper()})" for u in unclassified[:5])
            warnings.append(f"{len(unclassified)} asset không phân loại rõ nên KHÔNG đưa vào scope gate: {shown}"
                            + ("…" if len(unclassified) > 5 else ""))
        # Stable top-level keys: consumers must not dig into the raw provider payload.
        return entries, {"program": program, "assets": [entry.model_dump() for entry in entries],
                         "policy_text": policy_text, "policy_source": source,
                         "attempts": attempts, "completeness": completeness,
                         "classification": {"classified": len(entries), "unclassified_count": len(unclassified),
                                            "unclassified": unclassified[:100], "by_shape": by_shape[:100]},
                         "fetched_at": utc_now()}, warnings
