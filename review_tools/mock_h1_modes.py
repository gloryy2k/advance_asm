"""Review harness (not product code): the real app with an H1 provider backed by httpx.MockTransport, so the three
metadata sources can be compared without any network access.

  MODE=api|page|dump  SCR=/tmp/x  MOCK_PORT=18770  PYTHONPATH=. python review_tools/mock_h1_modes.py

api  : token configured, API answers.            page: no token, public page answers.
dump : no token, page unavailable (404), only the bounty-targets-data copy answers (no policy)."""
import os, sys, httpx, uvicorn
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend.config import Settings
from backend.main import create_app
from backend.jobs.h1_scope import HackerOneScopeProvider
from backend.jobs.scope_resolver import ScopeResolver

MODE = os.environ.get("MODE", "dump")
S = os.environ.get("SCR", f"/tmp/bbasm-n2-{MODE}")
PORT = int(os.environ.get("MOCK_PORT", "18770"))
os.makedirs(f"{S}/data", exist_ok=True); os.makedirs(f"{S}/targets", exist_ok=True)
extra = {"H1_USER": "u", "H1_TOKEN": "t"} if MODE == "api" else {}
settings = Settings(_env_file=None, BBASM_DATA=f"{S}/data", BBASM_TARGETS=f"{S}/targets", BBASM_STATIC=os.path.join(ROOT, "frontend/dist"),
                    BBASM_PORT=PORT, BBASM_SKIP_HISTORICAL=True, **extra)
POLICY = ("## Acme program policy\nAutomated scanning is allowed on in-scope web assets at up to 5 requests per second.\n"
          "No denial of service. No social engineering. Do not test /internal.")
SCOPES = [
    ("*.acme.com", "WILDCARD", True, "Main wildcard. Do not test /internal."),
    ("api.acme.com", "URL", True, "API. Rate limit 5 rps."),
    ("com.acme.android", "GOOGLE_PLAY_APP_ID", True, "Android app"),
    ("Open Scope", "OTHER", True, "Any other asset owned by Acme"),
    ("legacy.acme.com", "URL", False, "Retired"),
]
DUMP = [{"handle": "acme", "targets": {"in_scope": [{"asset_identifier": "*.acme.com", "asset_type": "WILDCARD", "eligible_for_submission": True},
                                                     {"asset_identifier": "*.acme.net", "asset_type": "WILDCARD", "eligible_for_submission": True}],
                                       "out_of_scope": []}}]

def handler(req):
    host = req.url.host
    if host == "api.hackerone.com":
        if req.url.path.endswith("structured_scopes"):
            return httpx.Response(200, json={"data": [{"attributes": {"asset_identifier": a, "asset_type": t, "eligible_for_submission": e, "instruction": i}} for a, t, e, i in SCOPES], "links": {}})
        return httpx.Response(200, json={"data": {"attributes": {"handle": "acme", "name": "Acme", "policy": POLICY}}})
    if host == "hackerone.com" and MODE == "page":
        edges = [{"node": {"asset_identifier": a, "asset_type": t, "eligible_for_submission": e, "instruction": i}} for a, t, e, i in SCOPES]
        return httpx.Response(200, json={"data": {"team": {"handle": "acme", "name": "Acme", "policy": POLICY,
                                                            "structured_scopes": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "edges": edges}}}})
    if host == "hackerone.com":
        return httpx.Response(404)
    if host == "raw.githubusercontent.com":
        return httpx.Response(200, json=DUMP)
    return httpx.Response(500)

app = create_app(settings)
app.state.scope_resolver = ScopeResolver(settings, app.state.database, HackerOneScopeProvider(settings, transport=httpx.MockTransport(handler)))
uvicorn.run(app, host="127.0.0.1", port=PORT, access_log=False, log_level="warning")
