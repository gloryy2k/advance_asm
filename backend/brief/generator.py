"""Bounded handoff brief, durable program instructions and safe folder scaffold."""
import json
from pathlib import Path
import re
import threading

from backend.db import utc_now
from backend.jobs.scope_resolver import ScopeError

USER_START = "<!-- user-editable -->"
USER_END = "<!-- /user-editable -->"
_lock = threading.RLock()


def clean(value, limit=250):
    return re.sub(r"[\r\n|]", " ", str(value or ""))[:limit]


class BriefGenerator:
    def __init__(self, settings, database):
        self.settings, self.database = settings, database

    def snapshot(self, slug, scan_id=None):
        if not self.database.path.exists():
            raise ScopeError("Program not found")
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM program WHERE slug=?", (slug,)).fetchone()
            if not row:
                raise ScopeError("Program not found")
            program = dict(row)
            if scan_id is None:
                scan = conn.execute("SELECT * FROM scan_run WHERE program_id=? AND status IN ('done','done_partial') ORDER BY id DESC LIMIT 1", (program["id"],)).fetchone()
            else:
                scan = conn.execute("SELECT * FROM scan_run WHERE program_id=? AND id=?", (program["id"], scan_id)).fetchone()
            if not scan:
                raise ScopeError("No completed scan available")
            scan = dict(scan)
            assets = [dict(r) for r in conn.execute("SELECT * FROM asset WHERE program_id=? AND last_seen_scan=? ORDER BY rank_score DESC,host", (program["id"], scan["id"]))]
            findings = [dict(r) for r in conn.execute("SELECT * FROM finding WHERE program_id=? AND last_seen_scan=? ORDER BY id", (program["id"], scan["id"]))]
        stats = json.loads(scan["stats_json"] or "{}")
        return program, scan, stats, assets, findings

    def target(self, slug):
        root = self.settings.BBASM_TARGETS.resolve()
        path = root / slug
        if path.is_symlink() or not path.resolve().is_relative_to(root) or path == root:
            raise ScopeError("Invalid target directory")
        return path

    @staticmethod
    def write(path, content):
        if path.is_symlink():
            raise ScopeError("Refusing to overwrite symlink")
        temporary = path.with_name(path.name + ".tmp")
        if temporary.is_symlink():
            raise ScopeError("Refusing temporary symlink")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)

    def generate(self, slug, scan_id=None):
        with _lock:
            program, scan, stats, assets, findings = self.snapshot(slug, scan_id)
            target = self.target(slug)
            target.mkdir(parents=True, exist_ok=True)
            for name in ("recon", "findings", "reports", "notes"):
                path = target / name
                if path.is_symlink():
                    raise ScopeError("Refusing scaffold symlink")
                path.mkdir(exist_ok=True)
            audit_path = target / "audit.jsonl"
            if audit_path.is_symlink():
                raise ScopeError("Refusing audit symlink")
            audit_path.touch(exist_ok=True)
            scope = stats.get("resolved_scope", [])
            scope_text = "# IN\n" + "\n".join(e["pattern"] for e in scope if e["kind"] == "in") + "\n# OUT\n" + "\n".join(e["pattern"] for e in scope if e["kind"] == "out") + "\n"
            self.write(target / ".scope", scope_text)
            program_path = target / "PROGRAM.md"
            if program_path.is_symlink():
                raise ScopeError("Refusing program symlink")
            if not program_path.exists():
                policy = json.loads(program["policy_json"] or "{}")
                policy_text = policy.get("policy") or policy.get("description") or "Không có policy công khai; bổ sung quy định trước khi hunt."
                body = f"# {slug}\n\n## Policy\n{policy_text}\n\n## Scope theo category\n"
                body += "\n".join(f"- {e['kind']} [{e['category']}] {e['pattern']}: {e.get('instruction', '')}" for e in scope)
                body += f"\n\n## Ghi chú của người dùng\n{USER_START}\nQuy định đặc biệt, auth, OOS và severity guideline: chưa bổ sung.\n{USER_END}\n"
                self.write(program_path, body)
            self.write(target / "CLAUDE.md", (Path(__file__).parent / "templates/CLAUDE.md").read_text(encoding="utf-8"))
            sections = [f"# AGENT BRIEF — {clean(slug)}\nScan {scan['id']} · {scan['depth']} · {scan['status']}\n",
                        "## SCOPE\n" + scope_text,
                        "## SỐ LIỆU\n" + f"Assets: {len(assets)} · Live: {stats.get('live', 0)} · URLs: {stats.get('urls', 0)} · Findings: {len(findings)}\n"]
            if scan["depth"] == "passive":
                sections.append("Depth=passive: chưa probe live/tech. Chạy lại light/strong để có surface đầy đủ.\n")
            if scan["status"] == "done_partial":
                sections.append("Scan có dữ liệu một phần; không suy ra host vắng là đã biến mất.\n")
            sections.extend(["## TOP SURFACE\n|Host|Rank|Status|Tech|\n|---|---:|---|---|\n",
                             "## ASSET MỚI\n", "## SIGNALS\n",
                             "## HƯỚNG TEST\nƯu tiên API/auth và signal có rank cao; xác minh thủ công, tuân thủ policy.\n",
                             "## CÁCH LÀM VIỆC\nĐọc PROGRAM.md để biết policy; dữ liệu recon ở recon/scans/" + str(scan["id"]) + "/. Ghi chú vào notes/, findings/ và reports/. Không tự submit.\n"])
            # Preserve all section headings and full scope. Overflow fails explicitly
            # instead of silently omitting scope rules from an apparently complete brief.
            if len("\n".join(sections).encode()) >= 12000:
                raise ScopeError("Scope exceeds 12KB brief budget; narrow the program scope")
            def append(index, line):
                if len(("\n".join(sections) + line).encode()) < 12000:
                    sections[index] += line
                    return True
                return False
            top = next(i for i, s in enumerate(sections) if s.startswith("## TOP"))
            new = top + 1
            signals = top + 2
            for entry in scope:
                if entry["category"] in {"mobile", "other"}:
                    append(signals, f"- Manual [{entry['category']}]: {clean(entry['pattern'])}; mobile: mobile-pentest.\n")
            for finding in findings[:20]:
                append(signals, f"- {finding['severity']} {finding['type']}: {clean(finding['name'], 120)}\n")
            for a in assets[:25]:
                status = a['status_code'] or '-' if scan['depth'] != 'passive' else '-'
                tech = clean(a['tech_json'], 70) if scan['depth'] != 'passive' else '-'
                append(top, f"|{clean(a['host'], 120)}|{a['rank_score'] or 0:g}|{status}|{tech}|\n")
            for a in assets:
                if a["first_seen_scan"] == scan["id"]:
                    append(new, f"- {clean(a['host'], 120)}\n")
            intel = target / "recon/scans" / str(scan["id"]) / "intel.json"
            if intel.is_file() and not intel.is_symlink():
                try:
                    result = json.loads(intel.read_text(encoding="utf-8"))
                    append(signals, "- Intel: " + clean(json.dumps(result, ensure_ascii=False), 700) + "\n")
                except (ValueError, OSError):
                    append(signals, "- Intel không khả dụng; không ảnh hưởng recon.\n")
            brief = "\n".join(sections)
            self.write(target / "AGENT_BRIEF.md", brief)
            return {"path": str(target / "AGENT_BRIEF.md"), "bytes": len(brief.encode()), "scan_id": scan["id"]}

    def update_program(self, slug, text):
        with _lock:
            self.snapshot(slug)
            path = self.target(slug) / "PROGRAM.md"
            if path.is_symlink() or not path.is_file():
                raise ScopeError("PROGRAM.md unavailable")
            old = path.read_text(encoding="utf-8")
            if old.count(USER_START) != 1 or old.count(USER_END) != 1 or USER_START in text or USER_END in text:
                raise ScopeError("Invalid user-editable markers")
            before, tail = old.split(USER_START)
            _, after = tail.split(USER_END)
            self.write(path, before + USER_START + "\n" + text.strip() + "\n" + USER_END + after)
