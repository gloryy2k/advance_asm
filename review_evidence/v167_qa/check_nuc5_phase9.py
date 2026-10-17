"""Run the verbatim recon_engine.sh Phase 9 with the real nuclei binary, offline on localhost."""
import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODE = 'with_home' if os.environ.get('QA_COPY_TEMPLATE_HOME') == '1' else 'default'
ROOT = Path('/qa/phase9') / MODE
OUT = ROOT / 'output'
ENGINE = Path('/opt/claude-bug-bounty/tools/recon_engine.sh')
SHIM = Path('/app/backend/shims')
(OUT / 'live').mkdir(parents=True, exist_ok=True)
(OUT / 'live' / 'urls.txt').write_text('http://127.0.0.1:8099\n', encoding='utf-8')

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'BBASM-NUC5-LOCAL-MATCH')
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 8099), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

official = ROOT / 'templates' / 'official'
official.mkdir(parents=True, exist_ok=True)
(official / 'nuc5.yaml').write_text('''id: bbasm-nuc5-local
info:
  name: BBASM NUC-5 localhost
  author: qa
  severity: high
  tags: bbasmqa,tech
http:
  - method: GET
    path:
      - "{{BaseURL}}/nuc5-check"
    matchers:
      - type: word
        words:
          - "BBASM-NUC5-LOCAL-MATCH"
''', encoding='utf-8')
if os.environ.get('QA_COPY_TEMPLATE_HOME') == '1':
    home_templates = ROOT / 'home' / 'nuclei-templates'
    shutil.copytree(official, home_templates, dirs_exist_ok=True)

# Record the effective argv, then exec the real nuclei binary. The tested BBASM shim remains first on PATH.
bin_dir = ROOT / 'bin'
bin_dir.mkdir(exist_ok=True)
wrapper = bin_dir / 'nuclei'
wrapper.write_text(f'#!/bin/bash\nprintf "%s\\n" "$@" > {ROOT}/nuclei.argv\nexec /usr/local/bin/nuclei "$@"\n', encoding='utf-8')
wrapper.chmod(0o755)

source = ENGINE.read_text(encoding='utf-8')
phase = source[source.index('log_info "Phase 9:'):source.index('# Phase 10:')]
phase = phase.rsplit('# ============================================================', 1)[0]
prefix = f'''#!/bin/bash
set -uo pipefail
log_info(){{ echo "[INFO] $1"; }}
log_step(){{ echo "[STEP] $1"; }}
log_warn(){{ echo "[WARN] $1"; }}
log_done(){{ echo "[DONE] $1"; }}
GREEN= RED= YELLOW= CYAN= NC=
BBASM_NUCLEI_ARGS=()
BB_AUTH_ARGS=()
'''
script = ROOT / 'phase9.sh'
script.write_text(prefix + phase + '\nprintf "QA_NUC_EXIT=%s\\n" "$NUC_EXIT"\n', encoding='utf-8')

assert not Path('/root/nuclei-templates').exists(), 'fixture must start without default HOME templates'
env = os.environ.copy()
env.update(PATH=f'{SHIM}:{bin_dir}:' + env['PATH'], RECON_DIR=str(OUT), RECON_OUT_DIR=str(OUT),
           BBASM_NUCLEI_OFFICIAL=str(official), BBASM_NUCLEI_AUTO_SELECT='1',
           BBASM_SKIP_NUCLEI='0', BBASM_NUC_SEV='high', QUICK_MODE='--quick',
           NUC_RATE_LIMIT='5', NUC_CONCURRENCY='1', NUC_BULK_SIZE='1', HOME='/root')
run = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True, timeout=120)
server.shutdown()

nuc = OUT / 'nuclei'
argv = (ROOT / 'nuclei.argv').read_text(encoding='utf-8').splitlines()
coverage = json.loads((nuc / 'coverage.json').read_text(encoding='utf-8'))
loaded = (nuc / 'templates_loaded.txt').read_text(encoding='utf-8')
stats = (nuc / 'stats.jsonl').read_text(encoding='utf-8')
findings_path = nuc / 'findings.jsonl'
findings = [json.loads(line) for line in findings_path.read_text(encoding='utf-8').splitlines()] if findings_path.exists() else []
print(json.dumps({'mode': MODE, 'argv_as': argv.count('-as'), 'argv_vv': argv.count('-vv'),
    'template_loaded_lines': len(loaded.splitlines()), 'loaded_jsonl_lines': sum(line.startswith('{') for line in loaded.splitlines()),
    'stats_lines': len(stats.splitlines()), 'stats_bytes': len(stats.encode()), 'findings': len(findings),
    'finding_ids': [x.get('template-id') for x in findings], 'coverage': coverage,
    'stats_tail': stats.splitlines()[-2:], 'log_tail': run.stdout.splitlines()[-8:]}, ensure_ascii=True))
assert run.returncode == 0 and '-as' in argv and '-vv' in argv, (run.returncode, argv, run.stdout, run.stderr)
assert coverage['failed'] is False and int(coverage['last_stats']['requests']) > 0, coverage
assert (nuc / 'templates_loaded.txt').is_file() and loaded.strip() and not any(line.startswith('{') for line in loaded.splitlines()), loaded
assert len(findings) >= 1 and all('127.0.0.1' in str(item) for item in findings), findings
assert Path('/root/nuclei-templates/nuc5.yaml').is_file(), 'shim did not populate default HOME templates'
