import pytest

from backend.config import Settings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None, BBASM_BBROOT=tmp_path / "framework",
        BBASM_DATA=tmp_path / "data", BBASM_TARGETS=tmp_path / "targets",
    )
