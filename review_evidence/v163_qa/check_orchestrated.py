"""Run a real BBASM JobRunner Strong scan, with only loopback HTTP and fake passive sources."""
import asyncio
import json
import os
import stat
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.db import Database
from backend.jobs.runner import JobRunner
from backend.jobs.scope_resolver import ScopeResolver
from backend.main import create_app
from backend.models import ResolveRequest

ROOT = Path('/qa/orchestrated')
ROOT.mkdir(parents=True, exist_ok=True)
FAKE_BIN = ROOT / 'home/go/bin'
FAKE_BIN.mkdir(parents=True, exist_ok=True)


def tool(name, script):
    path = FAKE_BIN / name
    path.write_text(script, encoding='utf-8')
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


tool('subfinder', '''#!/bin/sh
out=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then out="$2"; shift; fi
  shift
done
printf 'deep.qa.test\\n' > "$out"
''')
tool('curl', '#!/bin/sh\nprintf "[]\\n"\n')
tool('dig', '#!/bin/sh\nexit 0\n')
tool('httpx', '''#!/bin/sh
if [ "$1" = "-version" ]; then echo 'projectdiscovery.io httpx fixture'; exit 0; fi
list=""; out=""
while [ "$#" -gt 0 ]; do
  case "$1" in -l) list="$2"; shift;; -o) out="$2"; shift;; esac
  shift
done
while IFS= read -r host; do
  [ -n "$host" ] && printf 'http://%s [200] [100] [Fixture] [qa]\\n' "$host"
done < "$list" > "$out"
''')

os.environ['HOME'] = str(ROOT / 'home')
os.environ['PATH'] = str(FAKE_BIN) + ':' + os.environ['PATH']

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        with (ROOT / 'requests.log').open('a', encoding='utf-8') as stream:
            stream.write(f'{self.headers.get("Host")} {self.path}\n')
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'bbasm-loopback-fixture')
    def log_message(self, *_):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 80), Handler)
import threading
threading.Thread(target=server.serve_forever, daemon=True).start()

settings = Settings(_env_file=None, BBASM_DATA=ROOT / 'data', BBASM_TARGETS=ROOT / 'targets',
                    BBASM_BBROOT=Path('/opt/claude-bug-bounty'),
                    BBASM_NUCLEI_TEMPLATES=ROOT / 'data/nuclei-templates',
                    BBASM_UPDATE_TEMPLATES='0', BBASM_SKIP_HISTORICAL=True,
                    BBASM_SOURCE_TIMEOUT=5, BBASM_SCAN_TIMEOUT_STRONG=180)
official = settings.templates_dir / 'official'
official.mkdir(parents=True, exist_ok=True)
(official / '.bbasm-templates.json').write_text(json.dumps({'count': 1, 'source': 'localhost-fixture'}))
(official / 'qa.yaml').write_text('''id: bbasm-qa-orchestrated
info:
  name: BBASM orchestration fixture
  author: bbasm-qa
  severity: high
http:
  - method: GET
    path:
      - "{{BaseURL}}/nuclei-check"
    matchers:
      - type: status
        status: [200]
''', encoding='utf-8')

database = Database(settings.BBASM_DATA / 'bbasm.db')
database.migrate()
resolver = ScopeResolver(settings, database, Mock())
result = resolver.resolve(ResolveRequest(input='raw', scope=['*.qa.test', 'main.qa.test']))
config = result.config.model_copy(update={
    'depth': 'strong', 'scan_timeout': 180, 'threads': 2, 'rate_limit': 2,
    'nuclei_severity': 'high', 'skip_nmap': True, 'skip_nuclei': False,
    'skip_ffuf': True, 'skip_active_crawl': True, 'skip_takeover': True,
    'skip_secrets': True, 'skip_historical': True,
})

async def scenario():
    runner = JobRunner(settings, database)
    try:
        await runner.submit(result.scan_id, config, ack=True)
        await asyncio.wait_for(runner.queue.join(), timeout=175)
        return runner.status(result.scan_id)
    finally:
        await runner.close()

started = time.monotonic()
row = asyncio.run(scenario())
elapsed = time.monotonic() - started
with database.connect() as conn:
    slug = conn.execute('SELECT slug FROM program WHERE id=?', (row['program_id'],)).fetchone()[0]
root = settings.BBASM_TARGETS / slug / 'recon/scans' / str(result.scan_id)
coverage = {}
for path in root.glob('*/nuclei/coverage.json'):
    coverage[path.parent.parent.name] = json.loads(path.read_text())
app = create_app(settings)
response = TestClient(app).get(f'/api/scans/{result.scan_id}/phases')
report = response.json() if response.status_code == 200 else {}
nuclei = next((p for p in report.get('phases', []) if p.get('key') == 'nuclei'), {})
stats = json.loads(row['stats_json'] or '{}')
print(json.dumps({
    'scan_id': result.scan_id, 'status': row['status'], 'error': row['error'], 'elapsed_s': round(elapsed, 2),
    'stages': stats.get('stages'), 'coverage': coverage,
    'phase_http': response.status_code, 'phase': nuclei,
    'requests': (ROOT / 'requests.log').read_text().splitlines() if (ROOT / 'requests.log').exists() else [],
}, ensure_ascii=False))
server.shutdown()
assert response.status_code == 200
assert len(coverage) >= 2, f'Expected two real Phase9 outputs, got {list(coverage)}'
