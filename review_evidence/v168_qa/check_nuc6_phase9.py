"""Run the verbatim Phase 9 block with real nuclei, only inside an offline localhost container."""
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else 'normal300'
assert mode in {'normal300', 'timeout5', 'quick_default', 'full_default'}
root = Path('/qa/phase9') / mode
out = root / 'output'
(out / 'live').mkdir(parents=True, exist_ok=True)
count = 300 if mode in {'normal300', 'timeout5'} else 1
(out / 'live' / 'urls.txt').write_text(''.join(f'http://127.0.0.1:8099/item-{i}\n' for i in range(count)), encoding='utf-8')

seen = []
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        seen.append(self.path)
        if mode == 'timeout5':
            time.sleep(20)
        try:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'NUC-6-LOCAL-OK')
        except (BrokenPipeError, ConnectionResetError):
            pass
    def log_message(self, *args):
        pass

class Server(ThreadingHTTPServer):
    daemon_threads = True
server = Server(('127.0.0.1', 8099), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

template = root / 'nuc6.yaml'
template.write_text('''id: bbasm-nuc6-local
info:
  name: BBASM NUC-6 localhost
  author: qa
  severity: high
http:
  - method: GET
    path:
      - "{{BaseURL}}"
    matchers:
      - type: word
        words: ["NUC-6-LOCAL-OK"]
''', encoding='utf-8')

source = Path('/opt/claude-bug-bounty/tools/recon_engine.sh').read_text(encoding='utf-8')
phase = source[source.index('log_info "Phase 9:'):source.index('# Phase 10:')]
phase = phase.rsplit('# ============================================================', 1)[0]
prefix = f'''#!/bin/bash
set -uo pipefail
log_info(){{ echo "[INFO] $1"; }}
log_step(){{ echo "[STEP] $1"; }}
log_warn(){{ echo "[WARN] $1"; }}
log_done(){{ echo "[DONE] $1"; }}
GREEN= RED= YELLOW= CYAN= NC=
BBASM_NUCLEI_ARGS=(-t {template} -duc -ni)
BB_AUTH_ARGS=()
'''
script = root / 'phase9.sh'
script.write_text(prefix + phase + '\nprintf "QA_NUC_EXIT=%s\\n" "$NUC_EXIT"\n', encoding='utf-8')
env = os.environ.copy()
env.update(RECON_DIR=str(out), QUICK_MODE='' if mode == 'full_default' else '--quick',
           BBASM_SKIP_NUCLEI='0', BBASM_NUC_SEV='high', NUC_RATE_LIMIT='150',
           NUC_CONCURRENCY='50', NUC_BULK_SIZE='50')
env.pop('BBASM_NUCLEI_TIMEOUT', None)
if mode == 'timeout5':
    env['BBASM_NUCLEI_TIMEOUT'] = '5'
started = time.monotonic()
run = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True, timeout=45)
elapsed = time.monotonic() - started
server.shutdown()

nuc = out / 'nuclei'
targets = (nuc / 'targets.txt').read_text(encoding='utf-8').splitlines()
coverage = json.loads((nuc / 'coverage.json').read_text(encoding='utf-8'))
log = [line for line in run.stdout.splitlines() if line.startswith(('[INFO]', '[STEP]', '[WARN]', '[DONE]', 'QA_NUC_EXIT='))]
match = re.search(r'timeout=(\d+)s', run.stdout)
effective_timeout = int(match.group(1)) if match else None
assert run.returncode == 0 and len(targets) == count and coverage['live_urls'] == count and coverage['given_urls'] == count
assert coverage['limit'] == 0, coverage
if mode == 'timeout5':
    assert coverage['timed_out'] is True and effective_timeout == 5 and 4.5 <= elapsed <= 12, (coverage, effective_timeout, elapsed, log)
else:
    assert coverage['timed_out'] is False, coverage
    assert effective_timeout == (7200 if mode == 'full_default' else 3600), effective_timeout
print(json.dumps({'mode': mode, 'input_urls': count, 'targets_lines': len(targets), 'server_requests': len(seen),
    'coverage': {k: coverage[k] for k in ('live_urls', 'given_urls', 'limit', 'quick', 'timed_out', 'failed')},
    'effective_timeout_s': effective_timeout, 'elapsed_s': round(elapsed, 2),
    'stats_lines': len((nuc / 'stats.jsonl').read_text(encoding='utf-8').splitlines()), 'log': log[-6:]}, ensure_ascii=True))
