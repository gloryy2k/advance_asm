"""Hide two binaries only inside this disposable test container, then run pytest."""
from pathlib import Path
import pytest

for name in ('nuclei', 'ffuf'):
    path = Path('/usr/local/bin') / name
    assert path.is_file(), name
    path.rename(path.with_name(name + '.qa-hidden'))

raise SystemExit(pytest.main(['-q', '-m', 'not integration']))
