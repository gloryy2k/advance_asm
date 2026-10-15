"""V134_UI_LOGIC_AUDIT fixes that live in the API: URL scope, schedule defaults, kept policy, summary counts."""
import json

from fastapi.testclient import TestClient

from backend.main import create_app

POLICY = "Please add the header X-HackerOne-Research: <username> to all requests."


def seed_urls(settings):
    """Program 'acme' with a completed latest scan (#2) that saw nothing, and a URL only scan #1 saw."""
    client = TestClient(create_app(settings))
    client.__enter__()
    made = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["a.example.com"], "name": "acme", "policy_text": POLICY}).json()
    db = client.app.state.database
    with db.connect() as conn, conn:
        pid = conn.execute("SELECT id FROM program WHERE slug='acme'").fetchone()[0]
        conn.execute("UPDATE scan_run SET status='done' WHERE id=?", (made["scan_id"],))
        conn.execute("INSERT INTO scan_run(program_id,depth,status,trigger,stats_json) VALUES(?,'passive','done','manual','{}')", (pid,))
        conn.execute("INSERT INTO asset(program_id,host,state,category) VALUES(?,?,?,?)", (pid, "a.example.com", "active", "web"))
        conn.execute("INSERT INTO asset(program_id,host,status_code,state,category) VALUES(?,?,?,?,?)", (pid, "b.example.com", 200, "active", "web"))
        for url, first, last in (("https://a.example.com/old", 1, 1), ("https://a.example.com/api/x?id=1", 1, 1)):
            conn.execute("INSERT INTO url(program_id,url,source,first_seen_scan,last_seen_scan,score,tags_json) VALUES(?,?,?,?,?,?,?)", (pid, url, "gau", first, last, 2, "[]"))
    return client, made["scan_id"]


def test_url_lists_say_which_scans_they_speak_for(settings):
    client, first = seed_urls(settings)
    try:
        latest = client.get("/api/programs/acme/urls/summary").json()
        assert latest["total"] == 0 and latest["history_total"] == 2 and latest["latest"]["id"] == first + 1
        everything = client.get("/api/programs/acme/urls/summary?scan=all").json()
        assert everything["total"] == 2 and everything["funnel"] is None   # the funnel belongs to one scan only
        rows = client.get("/api/programs/acme/urls?scan=all&min_score=0").json()
        assert len(rows) == 2 and rows[0]["first_seen_scan"] == 1 and rows[0]["last_seen_scan"] == 1
        assert client.get("/api/programs/acme/urls?min_score=0").json() == []   # default is still the newest scan only
        assert len(client.get(f"/api/programs/acme/urls?scan={first}&min_score=0").json()) == 2   # known as of scan 1
        assert client.get("/api/programs/acme/urls?scan=0&min_score=0").json() == []
        assert client.get("/api/programs/acme/urls?scan=banana").status_code == 422
        export = client.get("/api/programs/acme/urls/export?scan=all")
        assert "https://a.example.com/old" in export.text and "-all" in export.headers["content-disposition"]
        assert "old" not in client.get("/api/programs/acme/urls/export").text
    finally:
        client.__exit__(None, None, None)


def test_summary_separates_inventory_from_http_live_and_names_header_hints(settings):
    client, _ = seed_urls(settings)
    try:
        s = client.get("/api/programs/acme/summary").json()
        assert s["assets_active"] == 2 and s["assets_live"] == 1 and s["assets_gone"] == 0
        assert s["request_header_hints"] == ["X-HackerOne-Research"]
    finally:
        client.__exit__(None, None, None)


def test_rescan_keeps_the_policy_the_user_pasted(settings):
    client, first = seed_urls(settings)
    try:
        assert client.get("/api/programs/acme").json()["policy"]["user_policy_text"] == POLICY
        # stored scope rows are what rescan re-resolves from
        with client.app.state.database.connect() as conn, conn:
            conn.execute("UPDATE scan_run SET status='done' WHERE id=?", (first,))
        again = client.post("/api/programs/acme/rescan").json()
        assert client.get("/api/programs/acme").json()["policy"]["user_policy_text"] == POLICY
        assert client.get(f"/api/scans/{again['scan_id']}/review").json()["request_header_hints"] == ["X-HackerOne-Research"]
        replaced = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["a.example.com"], "name": "acme", "policy_text": "New policy"}).json()
        assert client.get("/api/programs/acme").json()["policy"]["user_policy_text"] == "New policy" and replaced["scan_id"]
    finally:
        client.__exit__(None, None, None)


def test_schedule_uses_program_defaults_needs_consent_and_header_decision(settings):
    client, _ = seed_urls(settings)
    try:
        url = "/api/programs/acme/schedule"
        body = {"interval": "daily", "depth": "light", "enabled": True}
        denied = client.post(url, json=body)
        assert denied.status_code == 422 and denied.json()["error"]["code"] == "ack_required"
        denied = client.post(url, json=body | {"automation_ack": True})
        assert denied.status_code == 422 and denied.json()["error"]["code"] == "header_required"   # the bug: header was never applied
        client.put("/api/programs/acme/request-headers", json={"headers": ["X-HackerOne-Research: zz-user-4711"]})
        ok = client.post(url, json=body | {"automation_ack": True})
        assert ok.status_code == 200
        view = client.get("/api/programs/acme/summary").json()["schedule"]
        assert view["enabled"] == 1 and view["config"]["request_header_names"] == ["X-HackerOne-Research"] and "config_json" not in view
        assert "zz-user-4711" not in json.dumps(view["config"])   # names only
        # an explicit, named skip is the other way through
        client.put("/api/programs/acme/request-headers", json={"headers": []})
        skip = client.post(url, json=body | {"automation_ack": True, "skipped_headers": ["X-HackerOne-Research"]})
        assert skip.status_code == 200
        assert client.get("/api/programs/acme/summary").json()["schedule"]["config"]["skipped_headers"] == ["X-HackerOne-Research"]
        # turning it off keeps the stored configuration and asks for nothing
        off = client.post(url, json={"interval": "daily", "depth": "passive", "enabled": False})
        assert off.status_code == 200
        kept = client.get("/api/programs/acme/summary").json()["schedule"]
        assert kept["enabled"] == 0 and kept["config"]["depth"] == "light" and kept["config"]["skipped_headers"] == ["X-HackerOne-Research"]
    finally:
        client.__exit__(None, None, None)
