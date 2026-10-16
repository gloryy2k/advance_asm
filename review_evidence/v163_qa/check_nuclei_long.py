"""Exercise the verbatim Phase 9 block with real nuclei and localhost only."""
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path('/qa')
ENGINE = Path('/opt/claude-bug-bounty/tools/recon_engine.sh')
MODE = 'long300'
COUNT = 80
OUT = ROOT / 'nuclei_phase' / MODE
(OUT / 'live').mkdir(parents=True, exist_ok=True)
(OUT / 'live' / 'urls.txt').write_text(
    ''.join(f'http://127.0.0.1:8099/item-{i}\n' for i in range(COUNT)), encoding='utf-8'
)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(4)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'qa-localhost')
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 8099), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

template = ROOT / 'local-template.yaml'
template.write_text('''id: bbasm-local-qa\ninfo:\n  name: BBASM localhost fixture\n  author: bbasm-qa\n  severity: high\nhttp:\n  - method: GET\n    path:\n      - "{{BaseURL}}/nuclei-check"\n    matchers:\n      - type: status\n        status:\n          - 200\n''', encoding='utf-8')

source = ENGINE.read_text(encoding='utf-8')
phase = source[source.index('log_info "Phase 9:'):source.index('# Phase 10:')]
phase = phase.rsplit('# ============================================================', 1)[0]
prefix = '''#!/bin/bash\nset -uo pipefail\nlog_info(){ echo "[INFO] $1"; }\nlog_step(){ echo "[STEP] $1"; }\nlog_warn(){ echo "[WARN] $1"; }\nlog_done(){ echo "[DONE] $1"; }\nGREEN= RED= YELLOW= CYAN= NC=\nBBASM_NUCLEI_ARGS=(-t /qa/local-template.yaml -duc -ni)\nBB_AUTH_ARGS=()\n'''
if MODE == 'badtemplate':
    prefix = prefix.replace('/qa/local-template.yaml', '/qa/not-found-template.yaml')
prefix = prefix.replace('-duc -ni)', '-duc -ni -timeout 20)')
script = ROOT / 'phase9.sh'
script.write_text(prefix + phase + '\nprintf "QA_NUC_EXIT=%s\\n" "$NUC_EXIT"\n', encoding='utf-8')
env = os.environ.copy()
env.update(RECON_DIR=str(OUT), QUICK_MODE='--quick' if MODE == 'quick60' else '',
           BBASM_SKIP_NUCLEI='0', BBASM_NUC_SEV='high',
           NUC_RATE_LIMIT='1', NUC_CONCURRENCY='1', NUC_BULK_SIZE='1')
if MODE == 'timeout':
    bindir = ROOT / 'timeout_bin'
    bindir.mkdir(exist_ok=True)
    wrapper = bindir / 'timeout'
    wrapper.write_text('#!/bin/sh\nshift\nexec /usr/bin/timeout 1 "$@"\n', encoding='utf-8')
    wrapper.chmod(0o755)
    env['PATH'] = str(bindir) + ':' + env['PATH']
started = time.monotonic()
run = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True, timeout=500)
elapsed = time.monotonic() - started
server.shutdown()
coverage_path = OUT / 'nuclei' / 'coverage.json'
coverage = None
parse_error = None
if coverage_path.exists():
    try:
        coverage = json.loads(coverage_path.read_text(encoding='utf-8'))
    except ValueError as exc:
        parse_error = str(exc)
print(json.dumps({
    'mode': MODE, 'returncode': run.returncode, 'elapsed_s': round(elapsed, 2),
    'log': [line for line in run.stdout.splitlines() if line.startswith(('[INFO]', '[STEP]', '[WARN]', '[DONE]', 'QA_NUC_EXIT='))],
    'stderr': run.stderr[-600:], 'coverage_exists': coverage_path.exists(),
    'coverage': coverage, 'coverage_parse_error': parse_error,
    'stats_bytes': (OUT / 'nuclei' / 'stats.jsonl').stat().st_size if (OUT / 'nuclei' / 'stats.jsonl').exists() else None,
    'stats_lines': len((OUT / 'nuclei' / 'stats.jsonl').read_text(encoding='utf-8').splitlines()) if (OUT / 'nuclei' / 'stats.jsonl').exists() else None,
}, ensure_ascii=False))
