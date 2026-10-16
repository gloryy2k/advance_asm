import json
import shutil
from pathlib import Path

from backend.asm.results import summarize_nuclei

root = Path('/qa/nuclei_aggregate')
for step, mode in [('4', 'normal'), ('5', 'quick60')]:
    source = Path('/qa/nuclei_phase') / mode / 'nuclei'
    dest = root / step / 'nuclei'
    dest.mkdir(parents=True, exist_ok=True)
    for name in ['coverage.json', 'findings.jsonl']:
        shutil.copy2(source / name, dest / name)
print(json.dumps(summarize_nuclei(root), ensure_ascii=False))
