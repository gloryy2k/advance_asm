"""Execute the exact Phase 3 block from the pinned vendor engine with nmap fixture output."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path('/qa/eng')
ROOT.mkdir(parents=True, exist_ok=True)
engine = Path('/opt/claude-bug-bounty/tools/recon_engine.sh').read_text(encoding='utf-8')
phase = engine[engine.index('log_info "Phase 3: Port Scanning"'):engine.index('# Phase 4: URL Collection')]
phase = phase.rsplit('# ============================================================', 1)[0]
prefix = '''#!/bin/bash
set -uo pipefail
log_info(){ echo "[INFO] $1"; }
log_step(){ echo "[STEP] $1"; }
log_warn(){ echo "[WARN] $1"; }
log_done(){ echo "[DONE] $1"; }
nmap(){
  local normal="" greppable=""
  while [ "$#" -gt 0 ]; do
    case "$1" in -oN) normal="$2"; shift;; -oG) greppable="$2"; shift;; esac
    shift
  done
  printf 'fixture nmap\\n' > "$normal"
  cat > "$greppable" <<'EOF'
# Nmap scan initiated
Host: 127.0.0.1 (localhost)\tPorts: 80/open/tcp//http//nginx/, 443/open/tcp//ssl|http//nginx/, 8080/open/tcp//http-proxy//qa/, 22/closed/tcp//ssh///
Host: 127.0.0.2 (localhost2)\tPorts: 80/open/tcp//http//nginx/, 8443/open/tcp//ssl|http//qa/
# Nmap done
EOF
}
TARGET=127.0.0.1
TARGET_TYPE=ip
BBASM_SKIP_NMAP=0
BBASM_NMAP_CONNECT=1
BBASM_MANAGED=0
RECON_DIR=/qa/eng
mkdir -p "$RECON_DIR/ports"
'''
script = ROOT / 'phase3.sh'
script.write_text(prefix + phase, encoding='utf-8')
done = subprocess.run(['bash', str(script)], capture_output=True, text=True, timeout=15)
ports = (ROOT / 'ports/open_ports.txt').read_text(encoding='utf-8').splitlines()
expected = ['80/open', '443/open', '8080/open', '8443/open']
assert done.returncode == 0 and ports == expected, (done.returncode, ports, done.stdout, done.stderr)
assert '[DONE] Open ports: 4' in done.stdout
print(json.dumps({'exit': done.returncode, 'ports': ports, 'nmap_host_lines': 2,
                  'first_host_open_ports': 3, 'output_log': done.stdout.splitlines()}))
