import json
import shutil
from pathlib import Path

from backend.asm.phases import build_report, scan_root
from backend.config import Settings
from backend.tests.p2_helpers import environment

data = Path('/qa/nuc1_data')
targets = Path('/qa/nuc1_targets')
settings = Settings(_env_file=None, BBASM_DATA=data, BBASM_TARGETS=targets,
                    BBASM_BBROOT=Path('/app/vendor/claude-bug-bounty'))
db, _, result = environment(settings, ['127.0.0.1'])
with db.connect() as conn, conn:
    slug = conn.execute('SELECT p.slug FROM scan_run s JOIN program p ON p.id=s.program_id WHERE s.id=?',
                        (result.scan_id,)).fetchone()[0]
    conn.execute("UPDATE scan_run SET status='done_partial' WHERE id=?", (result.scan_id,))
root = scan_root(settings, slug, result.scan_id)
destination = root / '4' / 'nuclei'
destination.mkdir(parents=True, exist_ok=True)
source = Path('/qa/nuclei_phase/badtemplate/nuclei')
for name in ['coverage.json', 'findings.jsonl', 'stats.jsonl']:
    shutil.copy2(source / name, destination / name)
coverage = json.loads((destination / 'coverage.json').read_text(encoding='utf-8'))
phase = next(p for p in build_report(settings, db, result.scan_id)['phases'] if p['key'] == 'nuclei')
assert coverage['failed'] is True
assert phase['status'] == 'partial'
assert 'LỖI: nuclei không chạy được' in phase['detail']
assert '0 kết quả' not in phase['detail']
assert 'tự báo đã chạy' not in phase['detail']
assert '9223372036854775808' not in phase['detail']
assert 'n/a' not in phase['detail']
print(json.dumps({'status': phase['status'], 'detail': phase['detail'],
                  'failed': coverage['failed'], 'raw_last_stats': coverage['last_stats']}, ensure_ascii=False))
