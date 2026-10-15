"""P2 (Wolt #43): the server, not only the Review page, refuses Light/Strong when the policy names a header and none is set."""
import pytest

from backend.api.scans import require_headers
from backend.jobs.scope_resolver import ScopeError, default_config
from backend.trust import required_headers


def cfg(**kw):
    from backend.config import Settings
    base = default_config(Settings().model_copy(update={"BBASM_DEFAULT_DEPTH": kw.pop("depth", "light")}), [])
    return base.model_copy(update=kw)


HINT = ["X-HackerOne-Research"]


def test_blocks_active_depth_without_header():
    with pytest.raises(ScopeError) as err:
        require_headers(cfg(), HINT)
    assert err.value.code == "header_required"


def test_passes_with_header_case_insensitive_or_explicit_skip_or_passive():
    require_headers(cfg(request_headers=["x-hackerone-research: someone"]), HINT)
    require_headers(cfg(skip_required_headers=True), HINT)
    require_headers(cfg(depth="passive"), HINT)
    require_headers(cfg(), [])


def test_hint_detected_from_policy_text():
    assert required_headers({"policy_text": "Please add the header X-HackerOne-Research: <username> to all requests."}) == HINT
