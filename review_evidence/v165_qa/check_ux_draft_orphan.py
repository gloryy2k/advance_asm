"""Check explicit draft scan if an orphan output file exists before launch."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.asm.phases import scan_root
from backend.config import Settings
from backend.db import Database
from backend.main import create_app

root = Path('/qa/fixture2')
settings = Settings(_env_file=None, BBASM_DATA=root / 'data', BBASM_TARGETS=root / 'targets',
                    BBASM_BBROOT=Path('/opt/claude-bug-bounty'), BBASM_UPDATE_TEMPLATES='0')
db = Database(settings.BBASM_DATA / 'bbasm.db')
slug = 'example.com'
with db.connect() as conn:
    row = conn.execute("SELECT s.id,s.status FROM scan_run s JOIN program p ON p.id=s.program_id WHERE p.slug=? AND s.status='draft' ORDER BY s.id DESC LIMIT 1", (slug,)).fetchone()
    assert row is not None
    scan_id, status = row['id'], row['status']
assert status == 'draft'
file = scan_root(settings, slug, scan_id) / '4/ports/nmap_greppable.txt'
file.parent.mkdir(parents=True, exist_ok=True)
file.write_text('# Nmap scan initiated\nHost: 192.0.2.4 (orphan.example.com)\tPorts: 8080/open/tcp//http///\n# Nmap done\n')
ffuf = scan_root(settings, slug, scan_id) / '4/dirs/ffuf_orphan.json'
ffuf.parent.mkdir(parents=True, exist_ok=True)
ffuf.write_text(json.dumps({'results': [{'status': 200, 'length': 10, 'words': 2,
    'url': 'https://orphan.example.com/old', 'host': 'orphan.example.com'}]}))
with TestClient(create_app(settings)) as client:
    ports = client.get(f'/api/programs/{slug}/ports?scan={scan_id}')
    dirs = client.get(f'/api/programs/{slug}/dirs?scan={scan_id}')
assert ports.status_code == 200 and ports.json()['found'] is False, ports.json()
assert dirs.status_code == 200 and dirs.json()['found'] is False, dirs.json()
print(json.dumps({'scan_id': scan_id, 'scan_status': status,
                  'ports': {'http': ports.status_code, 'found': ports.json().get('found'), 'pairs': ports.json().get('pairs')},
                  'dirs': {'http': dirs.status_code, 'found': dirs.json().get('found'), 'total': dirs.json().get('total')}}))
