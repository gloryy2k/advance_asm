import json
import shutil
from pathlib import Path

from backend.asm.results import summarize_nuclei
from backend.asm.phases import structured_result

root = Path('/qa/nuclei_aggregate')
for step, mode in [('4', 'normal'), ('5', 'quick60')]:
    source = Path('/qa/nuclei_phase') / mode / 'nuclei'
    dest = root / step / 'nuclei'
    dest.mkdir(parents=True, exist_ok=True)
    for name in ['coverage.json', 'findings.jsonl']:
        shutil.copy2(source / name, dest / name)
summary = summarize_nuclei(root)
_, detail, _, _ = structured_result('nuclei', root)
assert summary['live_urls'] == 62 and summary['given_urls'] == 52
assert summary['limits'] == [50, 200]
assert 'mỗi lượt có giới hạn riêng: 50, 200 URL' in detail
assert 'giới hạn 200 URL mỗi lượt' not in detail
print(json.dumps({'live_urls': summary['live_urls'], 'given_urls': summary['given_urls'],
                  'limits': summary['limits'], 'detail': detail}, ensure_ascii=False))
