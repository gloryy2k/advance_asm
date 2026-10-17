"""Build the actual Run report from the real Phase 9 localhost output with inconsistent nuclei stats."""
import json
import shutil
from pathlib import Path
from unittest.mock import Mock

from backend.asm.phases import build_report, scan_root
from backend.config import Settings
from backend.db import Database
from backend.jobs.runner import JobRunner
from backend.jobs.scope_resolver import ScopeResolver
from backend.models import ResolveRequest

source = Path('/qa/phase9/default/output/nuclei')
coverage = json.loads((source / 'coverage.json').read_text(encoding='utf-8'))
assert coverage['failed'] is False and coverage['last_stats']['templates'] == '0'
assert int(coverage['last_stats']['requests']) > 0 and int(coverage['last_stats']['matched']) > 0

root = Path('/qa/report_fixture')
settings = Settings(_env_file=None, BBASM_DATA=root / 'data', BBASM_TARGETS=root / 'targets',
                    BBASM_BBROOT=Path('/opt/claude-bug-bounty'), BBASM_UPDATE_TEMPLATES='0')
db = Database(settings.BBASM_DATA / 'bbasm.db')
db.migrate()
draft = ScopeResolver(settings, db, Mock()).resolve(ResolveRequest(input='raw', scope=['127.0.0.1']))
JobRunner(settings, db).config(draft.scan_id, draft.config.model_copy(update={'depth': 'light', 'skip_nuclei': False}))
with db.connect() as conn, conn:
    conn.execute("UPDATE scan_run SET status='done', depth='light' WHERE id=?", (draft.scan_id,))
    slug = conn.execute('SELECT slug FROM program WHERE id=(SELECT program_id FROM scan_run WHERE id=?)',
                        (draft.scan_id,)).fetchone()[0]
target = scan_root(settings, slug, draft.scan_id) / '4' / 'nuclei'
target.mkdir(parents=True, exist_ok=True)
for name in ('coverage.json', 'stats.jsonl', 'findings.jsonl', 'templates_loaded.txt'):
    shutil.copyfile(source / name, target / name)
report = build_report(settings, db, draft.scan_id)
phase = next(p for p in report['phases'] if p['key'] == 'nuclei')
detail = phase['detail'] or ''
assert phase['status'] == 'ran' and phase['count'] == 1, phase
assert '1 request' in detail and 'không đáng tin' in detail, detail
assert 'đã chạy 0 template' not in detail, detail
print(json.dumps({'status': phase['status'], 'count': phase['count'], 'detail': detail,
                  'templates': phase['data']['templates'], 'templates_unreliable': phase['data']['templates_unreliable']}, ensure_ascii=True))
