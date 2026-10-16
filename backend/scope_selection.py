"""What the user chose at Review (hosts un-ticked, OUT rules typed by hand, asset groups switched off) belongs to the
program, not to one scan: Rescan and unattended schedules must start from it, and every place that decides "is this in
scope" must build its gate the same way."""
import json
from pathlib import Path

from backend.scope_gate import ScopeGate

NON_AUTO = {"mobile", "other"}


def selection_from_config(entries, config) -> dict:
    """The part of a launched configuration that is a decision about scope. `entries` are the resolved scope entries."""
    present = {e["category"] if isinstance(e, dict) else e.category for e in entries
               if (e["kind"] if isinstance(e, dict) else e.kind) == "in"} - NON_AUTO
    return {"excluded_hosts": list(config.excluded_hosts),
            "categories_disabled": sorted(present - set(config.categories_enabled))}


def read_selection(raw) -> dict:
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    return {"excluded_hosts": [str(x) for x in data.get("excluded_hosts", [])][:500],
            "categories_disabled": [str(x) for x in data.get("categories_disabled", [])]}


def apply_selection(config, entries, selection):
    """A configuration that keeps the program's stored exclusions. More exclusions only: never re-includes anything."""
    present = {e.category for e in entries if e.kind == "in"} - NON_AUTO
    enabled = [c for c in config.categories_enabled if c not in selection["categories_disabled"]] if config.categories_enabled else \
        sorted(present - set(selection["categories_disabled"]))
    excluded = list(dict.fromkeys([*config.excluded_hosts, *selection["excluded_hosts"]]))
    return config.model_copy(update={"categories_enabled": enabled, "excluded_hosts": excluded})


def effective_gate(entries, config, audit_path, settings) -> ScopeGate:
    """The one way a gate is built from a resolved scope plus a configuration (plan, export, schedule checks)."""
    items = [e if isinstance(e, dict) else e.model_dump() for e in entries]
    eligible = [e for e in items if e["category"] not in NON_AUTO]
    allow = [e["pattern"] for e in eligible if e["kind"] == "in" and e["category"] in config.categories_enabled]
    deny = [e["pattern"] for e in eligible if e["kind"] == "out"] + list(config.excluded_hosts)
    return ScopeGate(allow, deny, Path(audit_path), settings)
