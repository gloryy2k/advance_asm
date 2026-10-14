"""Disk-backed ZIP creation; bounded copy buffers, no symlink traversal."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from backend.db import utc_now
from backend.jobs.scope_resolver import ScopeError


URL_OR_HOST = re.compile(r"https?://[^\s\]\"'<>)]+|(?<![\w.-])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?![\w-])")
MAX_FILTER_BYTES = 50 * 1024 * 1024


def _filtered_copy(source, relative, gate, cache, out_dir, report):
    """Copy a recon file keeping only lines whose host passes the scope gate."""
    if source.stat().st_size > MAX_FILTER_BYTES or source.suffix.lower() not in {"", ".txt", ".json", ".jsonl", ".log", ".csv", ".md"}:
        report["files_skipped"].append(relative)
        return None
    target = out_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    kept = dropped = 0
    with source.open("r", encoding="utf-8", errors="replace") as src, target.open("w", encoding="utf-8", newline="\n") as dst:
        for line in src:
            match = URL_OR_HOST.search(line)
            allowed = True
            if match:
                token = match.group(0)
                if token not in cache:
                    try:
                        cache[token] = gate.in_scope(token)
                    except Exception:  # an unparseable token is not evidence the line is in scope
                        cache[token] = False
                allowed = cache[token]
            if allowed:
                dst.write(line)
                kept += 1
            else:
                dropped += 1
    report["lines_kept"] += kept
    report["lines_dropped"] += dropped
    return target


def build_export(generator, slug, include_recon=True, mode=None):
    """mode: "brief" (no recon), "filtered" (recon lines in scope only), "full" (raw recon, may include out-of-scope)."""
    mode = mode or ("full" if include_recon else "brief")
    if mode not in {"brief", "filtered", "full"}:
        raise ScopeError("mode phải là brief, filtered hoặc full")
    include_recon = mode != "brief"
    program, scan, stats, _, _ = generator.snapshot(slug)
    root = generator.target(slug)
    generator.generate(slug, scan["id"])
    selected = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise ScopeError("Export refuses symlinks")
        if any(p.startswith(".") and p != ".scope" for p in relative.parts):
            continue
        if path.name.endswith((".tmp", ".lock")) or path.name == "MANIFEST.json":
            continue
        if not include_recon and relative.parts[0] == "recon":
            continue
        if not path.resolve().is_relative_to(root.resolve()):
            raise ScopeError("Export path escapes target")
        selected.append((path, relative.as_posix()))
    report = {"mode": mode, "lines_kept": 0, "lines_dropped": 0, "files_skipped": []}
    staging = None
    if mode == "filtered":
        from backend.scope_gate import ScopeGate
        staging = Path(tempfile.mkdtemp(prefix="bbasm-export-filter-"))
        scope = stats.get("resolved_scope", [])
        eligible = [e for e in scope if e["category"] not in {"mobile", "other"}]
        gate = ScopeGate([e["pattern"] for e in eligible if e["kind"] == "in"], [e["pattern"] for e in eligible if e["kind"] == "out"],
                         staging / "gate-audit.jsonl", generator.settings)  # audit goes to scratch, not into the ZIP
        cache, rewritten = {}, []
        for path, relative in selected:
            parts = Path(relative).parts
            if parts[0] == "recon" and path.is_file():
                new = _filtered_copy(path, relative, gate, cache, staging, report)
                if new is not None:
                    rewritten.append((new, relative))
            else:
                rewritten.append((path, relative))
        selected = rewritten
    manifest = {"slug": slug, "source": program["source"], "handle": program["handle"],
                "scan_id": scan["id"], "depth": scan["depth"], "generated_at": utc_now(),
                "stats": {k: stats.get(k, 0) for k in ("subs", "live", "urls", "findings")},
                "scope": {kind: [e["pattern"] for e in stats.get("resolved_scope", []) if e["kind"] == kind] for kind in ("in", "out")},
                "files": [r for p, r in selected if p.is_file()] + ["MANIFEST.json"], "bbasm_version": "0.1.0",
                "recon": {**report, "raw_includes_out_of_scope": mode == "full",
                          "note": {"brief": "Không kèm recon.", "filtered": "Recon chỉ giữ các dòng có host trong scope.",
                                   "full": "Recon THÔ: có thể chứa URL/host ngoài scope. Không coi đó là dữ liệu hợp lệ."}[mode]}}
    temporary = tempfile.NamedTemporaryFile(prefix="bbasm-export-", suffix=".zip", delete=False)
    path = Path(temporary.name)
    temporary.close()
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr(slug + "/", "")
            for source, relative in selected:
                archive.write(source, slug + "/" + relative)
            archive.writestr(slug + "/MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        suffix = "" if mode == "full" else f"-{mode}"
        return path, f"bbasm-{slug}-scan{scan['id']}-{datetime.now(timezone.utc):%Y%m%d}{suffix}.zip"
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
