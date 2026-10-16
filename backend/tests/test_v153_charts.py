"""Numbers behind the Overview charts (trend across scans, status/tech/host distributions, severity matrix)."""
import json

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.tests.test_v152_lifecycle import program, settings_for


def test_charts_summarise_trend_and_current_inventory(settings):
    with TestClient(create_app(settings_for(settings))) as client:
        first = program(client)
        second = program(client, "acme")                        # same program: a second completed scan
        db = client.app.state.database
        with db.connect() as conn, conn:
            pid = conn.execute("SELECT id FROM program WHERE slug='acme'").fetchone()[0]
            for sid, stats in ((first, {"subs": 5, "live": 3, "urls": 40, "findings": 1}), (second, {"subs": 7, "live": 6, "urls": 90, "findings": 2})):
                conn.execute("UPDATE scan_run SET status='done', stats_json=? WHERE id=?", (json.dumps(stats), sid))
            for host, code, tech in (("a.example.com", 200, ["nginx", "php"]), ("b.example.com", 403, ["nginx"]), ("c.example.com", 503, []), ("d.example.com", None, None)):
                conn.execute("INSERT INTO asset(program_id,host,status_code,tech_json,state) VALUES(?,?,?,?,'active')", (pid, host, code, json.dumps(tech) if tech is not None else None))
            conn.execute("INSERT INTO asset(program_id,host,status_code,state) VALUES(?,?,?,'gone')", (pid, "old.example.com", 200))
            ids = {r["host"]: r["id"] for r in conn.execute("SELECT id,host FROM asset WHERE program_id=?", (pid,))}
            for i in range(3):
                conn.execute("INSERT INTO url(program_id,asset_id,url,score) VALUES(?,?,?,?)", (pid, ids["a.example.com"], f"https://a.example.com/{i}", 4.0 + i))
            conn.execute("INSERT INTO url(program_id,asset_id,url,score) VALUES(?,?,?,?)", (pid, ids["b.example.com"], "https://b.example.com/", 1))
            for severity, host in (("high", "a.example.com"), ("high", "a.example.com"), ("low", "b.example.com")):
                conn.execute("INSERT INTO finding(program_id,asset_id,type,severity,name) VALUES(?,?,?,?,?)", (pid, ids[host], "nuclei", severity, f"{host}-{severity}-{conn.total_changes}"))
            for change, n in (("new", 3), ("changed", 1)):
                for i in range(n):
                    conn.execute("INSERT INTO diff_event(program_id,scan_run_id,entity,entity_ref,change) VALUES(?,?,?,?,?)", (pid, second, "asset", f"h{i}", change))
        body = client.get("/api/programs/acme/charts").json()
        assert [t["id"] for t in body["trend"]] == sorted({first, second})
        last = body["trend"][-1]
        assert (last["hosts"], last["live"], last["urls"], last["findings"], last["new"], last["changed"], last["gone"]) == (7, 6, 90, 2, 3, 1, 0)
        assert body["status"]["classes"] == {"2xx": 1, "4xx": 1, "5xx": 1, "none": 1} and body["status"]["total"] == 4   # the gone host is not counted
        assert body["tech"][0] == {"name": "nginx", "count": 2}
        assert body["hosts_by_urls"][0] == {"host": "a.example.com", "urls": 3, "top_score": 6.0}
        matrix = body["severity_matrix"]
        assert matrix["hosts"][0]["host"] == "a.example.com" and matrix["hosts"][0]["high"] == 2 and matrix["hosts"][1]["low"] == 1
        assert client.get("/api/programs/nope/charts").status_code == 422


def test_charts_for_an_empty_program_are_empty_not_an_error(settings):
    with TestClient(create_app(settings_for(settings))) as client:
        program(client, launch=False)
        body = client.get("/api/programs/acme/charts").json()
        assert body["trend"] == [] and body["tech"] == [] and body["hosts_by_urls"] == [] and body["status"]["total"] == 0
