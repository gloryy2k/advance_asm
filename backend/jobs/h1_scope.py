"""Audited metadata transport and offline adapter for the pinned aggregator."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

import httpx

from backend.jobs.scope_resolver import ScopeError, classify
from backend.scope_gate import ScopeGate, audit

DUMP_URL = "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/hackerone_data.json"
API_BASE = "https://api.hackerone.com/v1/hackers/programs"
MAX_METADATA_BYTES = 50 * 1024 * 1024


class HackerOneScopeProvider:
    def __init__(self, settings, transport=None, run=None):
        self.settings = settings
        self.transport = transport
        self.run = run or subprocess.run

    def _get(self, client, gate, url, **kwargs):
        if not gate.in_scope(url):
            raise ScopeError("Metadata destination denied", "metadata_denied")
        # No redirects/proxies: never forward H1 credentials to another origin.
        with client.stream("GET", url, **kwargs) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_METADATA_BYTES:
                    raise ScopeError("Scope metadata exceeds size limit")
                chunks.append(chunk)
        return json.loads(b"".join(chunks))

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
    def _entries(program):
        targets = program.get("targets")
        if not isinstance(targets, dict) or not isinstance(targets.get("in_scope"), list) or not isinstance(targets.get("out_of_scope"), list):
            raise ScopeError("Cannot distinguish IN/OUT scope; refusing unlabelled output")
        result = []
        for key, kind in (("in_scope", "in"), ("out_of_scope", "out")):
            for asset in targets[key]:
                if isinstance(asset, str):
                    result.append(classify(asset, kind))
                elif isinstance(asset, dict) and isinstance(asset.get("asset_identifier"), str):
                    eligibility = asset.get("eligible_for_submission")
                    # Explicit ineligibility wins over the dump's pool label.
                    actual_kind = "out" if eligibility is False else kind
                    result.append(classify(asset["asset_identifier"], actual_kind,
                                           asset.get("asset_type"), asset.get("instruction") or ""))
                else:
                    raise ScopeError("Malformed scope asset")
        return result

    def resolve(self, handle: str, audit_path: Path):
        script = self.settings.tool_path("scope_aggregator.sh")
        if not script.is_file() or not self.settings.tool_path("scope_checker.py").is_file():
            raise ScopeError("Framework missing: run git submodule update --init", "framework_missing")
        gate = ScopeGate(["raw.githubusercontent.com", "api.hackerone.com"], [], audit_path, self.settings)
        warnings = []
        try:
            with httpx.Client(transport=self.transport, timeout=20, follow_redirects=False, trust_env=False) as client:
                program = None
                if self.settings.H1_TOKEN.get_secret_value() and self.settings.H1_USER.get_secret_value():
                    try:
                        program = self._api_program(client, gate, handle)
                    except (httpx.HTTPError, ScopeError, ValueError, KeyError, TypeError):
                        warnings.append("HackerOne API unavailable; using public metadata")
                if program is None:
                    program = self._public_program(client, gate, handle)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, ScopeError):
                raise
            # Do not expose tokens or remote response bodies in API errors.
            raise ScopeError("Scope metadata unavailable", "metadata_unavailable") from None
        entries = self._entries(program)
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
        return entries, {"program": program, "assets": [entry.model_dump() for entry in entries]}, warnings
