"""Independent UX-1 fixture: two finished scans, one draft, and the real HTTP routes."""
import json
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.asm.phases import scan_root
from backend.config import Settings
from backend.db import Database
from backend.jobs.scope_resolver import ScopeResolver
from backend.main import create_app
from backend.models import ResolveRequest

ROOT = Path('/qa/fixture2')
settings = Settings(_env_file=None, BBASM_DATA=ROOT / 'data', BBASM_TARGETS=ROOT / 'targets',
                    BBASM_BBROOT=Path('/opt/claude-bug-bounty'), BBASM_UPDATE_TEMPLATES='0')
db = Database(settings.BBASM_DATA / 'bbasm.db')
db.migrate()
resolver = ScopeResolver(settings, db, Mock())


def resolve(scope):
    result = resolver.resolve(ResolveRequest(input='raw', scope=scope))
    with db.connect() as conn:
        slug = conn.execute('SELECT p.slug FROM scan_run s JOIN program p ON p.id=s.program_id WHERE s.id=?', (result.scan_id,)).fetchone()[0]
    return result.scan_id, slug


def write(root, rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def ffuf(host, rows):
    return json.dumps({'results': [
        {'input': {'FUZZ': name}, 'status': status, 'length': length, 'words': words,
         'url': f'https://{host}/{name}', 'host': host}
        for name, status, length, words in rows]})


first, slug = resolve(['example.com'])
root1 = scan_root(settings, slug, first)
write(root1, '4/ports/nmap_greppable.txt',
      '# Nmap scan initiated\nHost: 192.0.2.10 (old.example.com)\tPorts: 80/open/tcp//http//nginx/, 443/open/tcp//ssl|http//nginx/\n# Nmap done\n')
write(root1, '4/dirs/ffuf_old.json', ffuf('old.example.com', [('old', 200, 100, 10)]))
with db.connect() as conn, conn:
    conn.execute("UPDATE scan_run SET status='done' WHERE id=?", (first,))

latest, slug2 = resolve(['example.com'])
assert slug2 == slug
root2 = scan_root(settings, slug, latest)
write(root2, '4/ports/nmap_greppable.txt',
      '# Nmap scan initiated\n'
      'Host: 104.18.1.10 (rpc.example.com)\tPorts: 80/open/tcp//http//Cloudflare http proxy/, 443/open/tcp//ssl|http//Cloudflare http proxy/, 1720/open/tcp//h323q931///, 8080/open/tcp//http-proxy//Cloudflare http proxy/\n'
      'Host: 104.18.1.11 (drpc.example.com)\tPorts: 80/open/tcp//http//Cloudflare http proxy/, 5060/open/tcp//sip///, 8443/open/tcp//ssl|http//Cloudflare http proxy/, 2000/closed/tcp//cisco-sccp///\n')
write(root2, '5/ports/nmap_greppable.txt',
      '# Nmap scan initiated\nHost: 192.0.2.7 (a.example.com)\tPorts: 22/open/tcp//ssh//OpenSSH 8.9/\n')
write(root2, '4/dirs/ffuf_rpc.json', ffuf('rpc.example.com',
      [(f'p{i}', 403, 4547, 656) for i in range(24)] + [('admin', 200, 812, 40), ('api', 301, 0, 1)]))
write(root2, '4/dirs/ffuf_only403.json', ffuf('only403.example.com',
      [(f'q{i}', 403, 4547, 656) for i in range(9)]))
with db.connect() as conn, conn:
    conn.execute("UPDATE scan_run SET status='done_partial' WHERE id=?", (latest,))

draft, _ = resolve(['example.com'])
other_draft, other_slug = resolve(['nodata.example.com'])

with TestClient(create_app(settings)) as client:
    base = f'/api/programs/{slug}'
    responses = {
        'ports_latest': client.get(base + '/ports?scan=latest'),
        'ports_first': client.get(base + f'/ports?scan={first}'),
        'ports_draft': client.get(base + f'/ports?scan={draft}'),
        'ports_missing': client.get(base + '/ports?scan=999999'),
        'dirs_latest': client.get(base + '/dirs?scan=latest'),
        'dirs_first': client.get(base + f'/dirs?scan={first}'),
        'dirs_draft': client.get(base + f'/dirs?scan={draft}'),
        'dirs_missing': client.get(base + '/dirs?scan=999999'),
        'ports_no_finished': client.get(f'/api/programs/{other_slug}/ports?scan=latest'),
        'dirs_no_finished': client.get(f'/api/programs/{other_slug}/dirs?scan=latest'),
    }
    assert all(r.status_code == 200 for r in responses.values())
    data = {key: response.json() for key, response in responses.items()}

assert data['ports_latest']['scan_id'] == latest and data['ports_latest']['pairs'] == 8
assert data['ports_latest']['hosts'] == 3 and data['ports_latest']['complete'] is False
assert data['ports_latest']['cdn_pairs'] == 7
assert data['ports_first']['scan_id'] == first and data['ports_first']['pairs'] == 2
assert data['dirs_latest']['scan_id'] == latest and data['dirs_latest']['total'] == 35
assert data['dirs_latest']['noise'] == 33 and data['dirs_latest']['significant'] == 2
assert data['dirs_first']['scan_id'] == first and data['dirs_first']['significant'] == 1
for key in ['ports_draft', 'ports_missing', 'dirs_draft', 'dirs_missing', 'ports_no_finished', 'dirs_no_finished']:
    assert data[key]['found'] is False, (key, data[key])

summary = {
    'slug': slug, 'first': first, 'latest': latest, 'draft': draft,
    'ports_latest': {k: data['ports_latest'][k] for k in ['scan_id', 'found', 'pairs', 'hosts', 'unique_ports', 'complete', 'cdn_pairs']},
    'ports_first': {k: data['ports_first'][k] for k in ['scan_id', 'found', 'pairs', 'hosts', 'unique_ports', 'complete']},
    'dirs_latest': {k: data['dirs_latest'][k] for k in ['scan_id', 'found', 'total', 'noise', 'significant', 'blocked_only']},
    'dirs_first': {k: data['dirs_first'][k] for k in ['scan_id', 'found', 'total', 'noise', 'significant']},
    'empty_cases': {k: {'found': data[k]['found'], 'scan_id': data[k]['scan_id']} for k in
                    ['ports_draft', 'ports_missing', 'dirs_draft', 'dirs_missing', 'ports_no_finished', 'dirs_no_finished']},
}
print(json.dumps(summary, ensure_ascii=False))
