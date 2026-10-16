"""Sitemap tree API: levels, A-Z / score / count order, filters, scan scope, nesting caps."""
import json

from fastapi.testclient import TestClient

from backend.main import create_app

URLS = [
    ("https://b.example.com/", 0, "observed", [], 2, 2),
    ("https://a.example.com/zeta/one", 1, "historical", [], 1, 1),
    ("https://a.example.com/Alpha/x?id=1", 4, "observed", ["api", "id-param"], 2, 2),
    ("https://a.example.com/Alpha/x?id=2", 4, "observed", ["api", "id-param"], 2, 2),
    ("https://a.example.com/Alpha/y/deep/file.js", 0, "historical", ["js"], 1, 2),
    ("https://a.example.com/alpha-two", 2, "historical", ["auth"], 1, 1),
    ("https://a.example.com/", 0, "observed", [], 2, 2),
    ("https://a.example.com:8443/admin/panel", 6, "observed", ["admin"], 2, 2),
    ("https://old.example.com/gone", 0, "historical", [], 1, 1),     # only seen by scan 1
]


def seeded(settings):
    client = TestClient(create_app(settings))
    client.__enter__()
    made = client.post("/api/scope/resolve", json={"input": "raw", "scope": ["*.example.com"], "name": "tree"}).json()
    with client.app.state.database.connect() as conn, conn:
        pid = conn.execute("SELECT id FROM program").fetchone()[0]
        conn.execute("UPDATE scan_run SET status='done' WHERE id=?", (made["scan_id"],))
        conn.execute("INSERT INTO scan_run(program_id,depth,status,trigger,stats_json) VALUES(?,'passive','done','manual','{}')", (pid,))
        for url, score, verification, tags, first, last in URLS:
            conn.execute("INSERT INTO url(program_id,url,source,first_seen_scan,last_seen_scan,score,verification,tags_json) VALUES(?,?,?,?,?,?,?,?)",
                         (pid, url, "gau", first, last, score, verification, json.dumps(tags)))
    return client


def names(response):
    return [n["display"] for n in response.json()["nodes"]]


def test_hosts_are_listed_a_to_z_with_subtree_counts(settings):
    client = seeded(settings)
    try:
        r = client.get("/api/programs/tree/urls/tree?scan=all")
        assert names(r) == ["a.example.com", "a.example.com:8443", "b.example.com", "old.example.com"]    # ports are separate nodes
        a = r.json()["nodes"][0]
        assert a["count"] == 6 and a["kind"] == "host" and a["has_children"] and a["self_count"] == 1 and a["url"] == "https://a.example.com/"
        assert r.json()["total"] == 4 and r.json()["truncated"] is False
    finally:
        client.__exit__(None, None, None)


def test_levels_sort_and_fold_query_variants(settings):
    client = seeded(settings)
    try:
        level = client.get("/api/programs/tree/urls/tree?scan=all&host=a.example.com&prefix=/").json()
        assert [n["display"] for n in level["nodes"]] == ["Alpha", "alpha-two", "zeta"]                  # case-insensitive A-Z
        alpha = level["nodes"][0]
        assert alpha["kind"] == "dir" and alpha["count"] == 3 and alpha["max_score"] == 4 and alpha["tags"] == ["api", "id-param", "js"]
        inner = client.get("/api/programs/tree/urls/tree?scan=all&host=a.example.com&prefix=/Alpha").json()
        assert [n["display"] for n in inner["nodes"]] == ["x", "y"]
        x = inner["nodes"][0]
        assert x["kind"] == "file" and x["count"] == 2 and x["variants"] == 2 and x["verification"] == "observed"   # ?id=1, ?id=2 fold into one node
        deep = client.get("/api/programs/tree/urls/tree?scan=all&host=a.example.com&prefix=/Alpha/y/deep").json()
        assert [n["display"] for n in deep["nodes"]] == ["file.js"] and deep["nodes"][0]["url"].endswith("/file.js")
        folders = client.get("/api/programs/tree/urls/tree?scan=all&host=a.example.com&folders_first=true").json()
        assert [n["display"] for n in folders["nodes"]] == ["Alpha", "zeta", "alpha-two"]               # folders first, each group A-Z
        by_score = client.get("/api/programs/tree/urls/tree?scan=all&host=a.example.com&sort=score").json()
        assert [n["display"] for n in by_score["nodes"]] == ["Alpha", "alpha-two", "zeta"]
        by_count = client.get("/api/programs/tree/urls/tree?scan=all&host=a.example.com&sort=count").json()
        assert by_count["nodes"][0]["display"] == "Alpha"
    finally:
        client.__exit__(None, None, None)


def test_scan_scope_filters_and_paging_follow_the_url_list(settings):
    client = seeded(settings)
    try:
        latest = client.get("/api/programs/tree/urls/tree").json()               # newest completed scan (#2) only
        assert [n["display"] for n in latest["nodes"]] == ["a.example.com", "a.example.com:8443", "b.example.com"]
        as_of_1 = client.get("/api/programs/tree/urls/tree?scan=1").json()
        assert "old.example.com" in [n["display"] for n in as_of_1["nodes"]]
        filtered = client.get("/api/programs/tree/urls/tree?scan=all&tag=api").json()
        assert [n["display"] for n in filtered["nodes"]] == ["a.example.com"] and filtered["nodes"][0]["count"] == 2
        searched = client.get("/api/programs/tree/urls/tree?scan=all&q=panel").json()
        assert [n["display"] for n in searched["nodes"]] == ["a.example.com:8443"]
        score = client.get("/api/programs/tree/urls/tree?scan=all&min_score=4").json()
        assert [n["display"] for n in score["nodes"]] == ["a.example.com", "a.example.com:8443"]
        page = client.get("/api/programs/tree/urls/tree?scan=all&limit=2&offset=2").json()
        assert [n["display"] for n in page["nodes"]] == ["b.example.com", "old.example.com"] and page["total"] == 4
        assert client.get("/api/programs/tree/urls/tree?scan=banana").status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_depth_returns_nested_levels_and_the_node_cap_is_reported(settings, monkeypatch):
    client = seeded(settings)
    try:
        nested = client.get("/api/programs/tree/urls/tree?scan=all&depth=3&host=a.example.com").json()
        alpha = nested["nodes"][0]
        assert [c["display"] for c in alpha["children"]] == ["x", "y"]
        assert alpha["children"][1]["children"][0]["display"] == "deep"
        import backend.sitemap as sitemap
        monkeypatch.setattr(sitemap, "MAX_NODES", 3)
        capped = client.get("/api/programs/tree/urls/tree?scan=all&depth=3").json()
        assert capped["truncated"] is True
    finally:
        client.__exit__(None, None, None)


def test_a_large_inventory_is_served_one_level_at_a_time(settings):
    import time
    client = seeded(settings)
    try:
        with client.app.state.database.connect() as conn, conn:
            pid = conn.execute("SELECT id FROM program").fetchone()[0]
            conn.executemany("INSERT INTO url(program_id,url,source,first_seen_scan,last_seen_scan,score,verification,tags_json) VALUES(?,?,?,?,?,?,?,?)",
                             [(pid, f"https://big.example.com/section{i % 40}/item{i}", "gau", 2, 2, i % 5, "historical", "[]") for i in range(20000)])
        started = time.time()
        top = client.get("/api/programs/tree/urls/tree?scan=all&host=big.example.com").json()
        assert time.time() - started < 2.0 and top["total"] == 40 and top["nodes"][0]["count"] == 500
        capped = client.get("/api/programs/tree/urls/tree?scan=all&host=big.example.com&prefix=/section1&limit=200").json()
        assert len(capped["nodes"]) == 200 and capped["total"] == 500           # a folder with 500 children is paged, never dumped
    finally:
        client.__exit__(None, None, None)


def test_a_search_can_open_a_path_as_deep_as_it_needs(settings):
    """Host QA (24f0c03): a file under 4 nested folders must be reachable by one search request."""
    client = seeded(settings)
    try:
        with client.app.state.database.connect() as conn, conn:
            pid = conn.execute("SELECT id FROM program").fetchone()[0]
            conn.execute("INSERT INTO url(program_id,url,source,first_seen_scan,last_seen_scan,score,verification,tags_json) VALUES(?,?,?,?,?,?,?,?)",
                         (pid, "https://alpha.example.com/a7/b9/c3/d5/e1/f2/item0999?v=0", "gau", 2, 2, 1, "historical", "[]"))
        r = client.get("/api/programs/tree/urls/tree?scan=all&q=item0999&depth=12").json()
        node = r["nodes"][0]
        trail = [node["display"]]
        while node["children"]:
            node = node["children"][0]
            trail.append(node["display"])
        assert trail == ["alpha.example.com", "a7", "b9", "c3", "d5", "e1", "f2", "item0999"] and r["matched"] == 1 and r["truncated"] is False
        assert client.get("/api/programs/tree/urls/tree?scan=all&depth=13").status_code == 422
    finally:
        client.__exit__(None, None, None)
