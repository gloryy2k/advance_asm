"""Review harness (not product code): real app + real uvicorn on :18766 with an H1 provider
backed by httpx.MockTransport (no internet). Usage:
  cd frontend && npm run build && cd ..
  SCR=/tmp/bbasm-mock python review_tools/mock_h1_server.py   # then open http://127.0.0.1:18766
"""
import os, sys, httpx, uvicorn
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.config import Settings
from backend.main import create_app
from backend.jobs.h1_scope import HackerOneScopeProvider
from backend.jobs.scope_resolver import ScopeResolver
S = os.environ.get("SCR", "/tmp/bbasm-mock")
os.makedirs(f"{S}/h1run/data", exist_ok=True); os.makedirs(f"{S}/h1run/targets", exist_ok=True)
settings = Settings(_env_file=None, BBASM_DATA=f"{S}/h1run/data", BBASM_TARGETS=f"{S}/h1run/targets",
    BBASM_STATIC=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend/dist"), BBASM_PORT=18766, BBASM_SKIP_HISTORICAL=True,
    H1_USER="u", H1_TOKEN="t")
scopes = [
 ("*.acme.com","WILDCARD",True,"Main wildcard. Do not test /internal."),
 ("api.acme.com","URL",True,"API. Rate limit 5 rps."),
 ("https://github.com/acme/webapp","SOURCE_CODE",True,"Read only"),
 ("com.acme.android","GOOGLE_PLAY_APP_ID",True,"Android app"),
 ("198.51.100.0/24","CIDR",True,""),
 ("legacy.acme.com","URL",False,"Out of scope: legacy"),
 ("*.corp.acme.com","WILDCARD",False,"Internal"),
]
def handler(req):
    if req.url.path.endswith("structured_scopes"):
        return httpx.Response(200, json={"data":[{"attributes":{"asset_identifier":a,"asset_type":t,"eligible_for_submission":e,"instruction":i}} for a,t,e,i in scopes],"links":{}})
    return httpx.Response(200, json={"data":{"attributes":{"handle":"acme","name":"Acme","policy":"## Acme policy\nNo DoS. No social engineering. Automated scanning limited to 5 req/s. Report via HackerOne only."}}})
app = create_app(settings)
app.state.scope_resolver = ScopeResolver(settings, app.state.database, HackerOneScopeProvider(settings, transport=httpx.MockTransport(handler)))
uvicorn.run(app, host="127.0.0.1", port=18766, access_log=False, log_level="warning")
