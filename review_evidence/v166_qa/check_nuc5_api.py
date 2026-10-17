"""NUC-5 API fixture: real installed nuclei lists three local templates by tag."""
import json
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.db import Database
from backend.jobs.scope_resolver import ScopeResolver
from backend.main import create_app
from backend.models import ResolveRequest

root = Path('/qa/fixture')
templates = root / 'templates' / 'official' / 'http' / 'qa'
templates.mkdir(parents=True, exist_ok=True)
for slug, name, severity, tags in [
    ('a', 'QA Alpha', 'low', 'bbasmqa,tech'),
    ('b', 'QA Beta', 'medium', 'bbasmqa,tech'),
    ('c', 'QA Other', 'info', 'otherqa'),
]:
    (templates / f'{slug}.yaml').write_text(f'''id: qa-{slug}
info:
  name: {name}
  author: qa
  severity: {severity}
  tags: {tags}
http:
  - method: GET
    path:
      - "{{{{BaseURL}}}}/nuc5-{slug}"
    matchers:
      - type: status
        status: [200]
''', encoding='utf-8')
(root / 'templates' / 'official' / '.bbasm-templates.json').write_text(json.dumps({'count': 3}), encoding='utf-8')
settings = Settings(_env_file=None, BBASM_DATA=root / 'data', BBASM_TARGETS=root / 'targets',
    BBASM_BBROOT=Path('/opt/claude-bug-bounty'), BBASM_NUCLEI_TEMPLATES=root / 'templates', BBASM_UPDATE_TEMPLATES='0')
db = Database(settings.BBASM_DATA / 'bbasm.db')
db.migrate()
draft = ScopeResolver(settings, db, Mock()).resolve(ResolveRequest(input='raw', scope=['127.0.0.1']))

with TestClient(create_app(settings)) as client:
    found = client.get('/api/tools/templates/lookup?tag=bbasmqa')
    none = client.get('/api/tools/templates/lookup?tag=absentqa')
    invalid = client.get('/api/tools/templates/lookup?tag=bad%20tag!')

assert found.status_code == 200, found.text
assert found.json()['total'] == 2, found.json()
assert {(x['name'], x['severity'], x['path']) for x in found.json()['templates']} == {
    ('QA Alpha', 'low', 'http/qa/a.yaml'), ('QA Beta', 'medium', 'http/qa/b.yaml')}, found.json()
assert none.status_code == 200 and none.json()['total'] == 0 and none.json()['templates'] == [], none.text
assert invalid.status_code == 422 and invalid.json()['error']['code'] == 'invalid_tag', invalid.text
print(json.dumps({'draft': draft.scan_id, 'found': found.json(), 'absent': none.json(),
                  'invalid': {'status': invalid.status_code, 'code': invalid.json()['error']['code']}}, ensure_ascii=True))
