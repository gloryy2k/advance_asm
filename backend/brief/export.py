"""Disk-backed ZIP creation; bounded copy buffers, no symlink traversal."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import zipfile

from backend.db import utc_now
from backend.jobs.scope_resolver import ScopeError


def build_export(generator, slug, include_recon=True):
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
    manifest = {"slug": slug, "source": program["source"], "handle": program["handle"],
                "scan_id": scan["id"], "depth": scan["depth"], "generated_at": utc_now(),
                "stats": {k: stats.get(k, 0) for k in ("subs", "live", "urls", "findings")},
                "scope": {kind: [e["pattern"] for e in stats.get("resolved_scope", []) if e["kind"] == kind] for kind in ("in", "out")},
                "files": [r for p, r in selected if p.is_file()] + ["MANIFEST.json"], "bbasm_version": "0.1.0"}
    temporary = tempfile.NamedTemporaryFile(prefix="bbasm-export-", suffix=".zip", delete=False)
    path = Path(temporary.name)
    temporary.close()
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr(slug + "/", "")
            for source, relative in selected:
                archive.write(source, slug + "/" + relative)
            archive.writestr(slug + "/MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        return path, f"bbasm-{slug}-scan{scan['id']}-{datetime.now(timezone.utc):%Y%m%d}.zip"
    except BaseException:
        path.unlink(missing_ok=True)
        raise
