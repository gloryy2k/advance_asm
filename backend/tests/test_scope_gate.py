import json

import pytest

from backend.config import PROJECT_ROOT
from backend.scope_gate import ScopeGate


@pytest.fixture
def gate(settings, tmp_path):
    settings.BBASM_BBROOT = PROJECT_ROOT / "vendor/claude-bug-bounty"
    return ScopeGate(["*.acme.com", "acme.com", "1.2.3.0/24", "2001:db8::/32"],
                     ["blocked.acme.com", "1.2.3.99", "2001:db8:bad::/48"],
                     tmp_path / "audit.jsonl", settings)


@pytest.mark.parametrize("target,allowed", [
    ("sub.acme.com", True), ("evil-acme.com", False), ("acme.com", True),
    ("new.acme.com", True), ("a.b.acme.com", True), ("blocked.acme.com", False),
    ("acme.com.attacker.net", False), ("https://SUB.ACME.COM:8443/path?q=x", True),
    ("1.2.3.45", True), ("1.2.4.1", False), ("1.2.3.99", False),
    ("https://1.2.3.45:443/path", True), ("1.2.3.0/25", False),
    ("1.2.3.128/25", True), ("1.2.0.0/16", False),
    ("2001:db8::1", True), ("https://[2001:db8::1]:443/path", True),
    ("2001:db8:bad::1", False), ("2001:db8::/32", False),
    ("2001:db9::1", False), ("acme.com.", True),
    ("https://acme.com@evil.com", False), ("https://evil.com@acme.com", False),
    ("https://acme.com:99999", False), ("https://acme.com\\@evil.com", False),
    ("*.acme.com", False), ("", False), ("acme.com\n", False),
    ("file:///acme.com", False), ("https://acme%2ecom", False),
])
def test_tc_sg_1_through_8_and_malformed_targets(gate, target, allowed):
    assert gate.in_scope(target) is allowed
    records = [json.loads(line) for line in gate.audit_path.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["decision"] == ("allow" if allowed else "deny")
    assert records[0]["ts"].endswith("Z")
    assert records[0]["rule"]


def test_wildcard_does_not_grant_apex(gate):
    gate.allow = ["*.acme.com"]
    assert not gate.in_scope("acme.com")


def test_repo_scope_does_not_grant_other_repositories(gate):
    gate.allow = ["repo:https://github.com/acme/project"]
    assert gate.in_scope("https://github.com/acme/project.git")
    assert gate.in_scope("https://github.com/acme/project/tree/main")
    for target in ("https://github.com/acme/project-other", "https://github.com/other/project",
                   "https://github.com/acme/project/../other", "https://github.com/acme/project/%2e%2e/other",
                   "https://github.com", "http://github.com/acme/project"):
        assert not gate.in_scope(target)


def test_audit_failure_does_not_allow_outbound(gate, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr("backend.scope_gate.audit", fail)
    with pytest.raises(OSError):
        gate.in_scope("acme.com")
