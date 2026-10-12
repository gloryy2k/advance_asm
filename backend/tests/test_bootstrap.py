import json
from types import SimpleNamespace
from unittest.mock import Mock
import subprocess

from backend.bootstrap import bootstrap


def test_startup_migrates_and_audits_template_update(settings, monkeypatch):
    monkeypatch.setattr("backend.bootstrap.shutil.which", lambda *a, **k: "/tools/nuclei")
    run = Mock(return_value=SimpleNamespace(returncode=0))
    bootstrap(settings, run)
    assert (settings.BBASM_DATA / "bbasm.db").is_file()
    run.assert_called_once()
    assert run.call_args.kwargs["timeout"] == 120
    assert json.loads((settings.BBASM_DATA / "audit.jsonl").read_text())["rule"] == "template_update"


def test_startup_update_failure_and_disable_are_soft(settings, monkeypatch):
    monkeypatch.setattr("backend.bootstrap.shutil.which", lambda *a, **k: "/tools/nuclei")
    bootstrap(settings, Mock(side_effect=subprocess.TimeoutExpired("nuclei", 120)))
    monkeypatch.setenv("BBASM_UPDATE_TEMPLATES", "0")
    run = Mock()
    bootstrap(settings, run)
    run.assert_not_called()
