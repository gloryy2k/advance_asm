import pytest
from pydantic import ValidationError

from backend.config import PROJECT_ROOT, Settings


def test_safe_defaults():
    settings = Settings(_env_file=None)
    assert settings.BBASM_BIND == "127.0.0.1"
    assert settings.BBASM_DEFAULT_DEPTH == "light"
    assert settings.BB_THREADS == 50
    assert settings.BB_RATE_LIMIT == 150
    assert settings.BBASM_MAX_CONCURRENT_SCANS == 2
    assert [settings.scan_timeout(d) for d in ("passive", "light", "strong")] == [300, 900, 2700]
    assert settings.tool_path("recon_engine.sh") == PROJECT_ROOT / "vendor/claude-bug-bounty/tools/recon_engine.sh"
    assert settings.H1_TOKEN.get_secret_value() == ""


def test_dotenv_and_environment_precedence(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "BB_THREADS=12\nBBASM_TOOLS_SUBDIR=bughunter/tools\n"
        "BBASM_DEFAULT_DEPTH=passive # inline comment\nSUBFINDER_CONFIG_DIR=\n"
        "H1_TOKEN=test-secret\nCORS_ORIGINS=http://localhost:5173, http://localhost:8000\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BB_THREADS", "25")
    settings = Settings(_env_file=dotenv)
    assert settings.BB_THREADS == 25
    assert settings.BBASM_DEFAULT_DEPTH == "passive"
    assert settings.SUBFINDER_CONFIG_DIR is None
    assert settings.tool_path("recon_engine.sh") == settings.BBASM_BBROOT / "bughunter/tools/recon_engine.sh"
    assert settings.cors_origins == ["http://localhost:5173", "http://localhost:8000"]
    assert "test-secret" not in repr(settings)


@pytest.mark.parametrize("name,value", [
    ("BB_THREADS", "201"), ("BB_RATE_LIMIT", "501"),
    ("BBASM_SCAN_TIMEOUT_LIGHT", "0"), ("BBASM_MAX_CONCURRENT_SCANS", "0"),
    ("BBASM_DEFAULT_DEPTH", "deep"), ("BBASM_PORT", "65536"),
    ("BBASM_TOOLS_SUBDIR", "../tools"), ("BBASM_TOOLS_SUBDIR", "/tools"),
    ("BBASM_TOOLS_SUBDIR", "C:\\tools"),
])
def test_invalid_config_fails_at_startup(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_checked_in_env_example_is_valid():
    settings = Settings(_env_file=PROJECT_ROOT / ".env.example")
    assert settings.BBASM_DEFAULT_DEPTH == "light"
    assert settings.SUBFINDER_CONFIG_DIR is None
