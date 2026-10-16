import json
import shutil
from pathlib import Path

from backend.asm.phases import build_report, scan_root
from backend.config import Settings
from backend.tests.p2_helpers import environment

settings = Settings(_env_file=None, BBASM_DATA=Path('/qa/nuc2_data'),
                    BBASM_TARGETS=Path('/qa/nuc2_targets'),
                    BBASM_BBROOT=Path('/app/vendor/claude-bug-bounty'))
db, _, result = environment(settings, ['127.0.0.1'])
with db.connect() as conn, conn:
    slug = conn.execute('SELECT p.slug FROM scan_run s JOIN program p ON p.id=s.program_id WHERE s.id=?',
                        (result.scan_id,)).fetchone()[0]
    conn.execute("UPDATE scan_run SET status='done' WHERE id=?", (result.scan_id,))
root = scan_root(settings, slug, result.scan_id)
for step, mode in [('4', 'quick60'), ('5', 'normal')]:
    source = Path('/qa/nuclei_phase') / mode / 'nuclei'
    dest = root / step / 'nuclei'
    dest.mkdir(parents=True, exist_ok=True)
    for name in ['coverage.json', 'findings.jsonl']:
        shutil.copy2(source / name, dest / name)
phase = next(p for p in build_report(settings, db, result.scan_id)['phases'] if p['key'] == 'nuclei')
assert phase['status'] == 'ran'
assert phase['count'] == 52
assert 'mỗi lượt có giới hạn riêng: 50, 200 URL' in phase['detail']
assert 'giới hạn 200 URL mỗi lượt' not in phase['detail']
print(json.dumps({'status': phase['status'], 'count': phase['count'],
                  'detail': phase['detail']}, ensure_ascii=False))
