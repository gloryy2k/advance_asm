"""V5: URL triage, scope-gate funnel, and the inventory API."""
import json

from fastapi.testclient import TestClient

from backend.asm.urlintel import classify_url, url_shape
from backend.jobs.ingest import Ingester
from backend.jobs.recon_orch import ReconOrchestrator
from backend.main import create_app
from backend.tests.p2_helpers import environment, write_output


def test_tc_url_1_classification_and_shape():
    tags, score = classify_url("https://x.com/api/v1/users?id=5&next=/a")
    assert {"api", "params", "id-param", "redirect-param"} <= set(tags) and score >= 6
    assert classify_url("https://x.com/img/logo.png") == (["static"], 0.0)
    assert "sensitive" in classify_url("https://x.com/.env")[0] and "sensitive" in classify_url("https://x.com/db.sql.bak")[0]
    assert classify_url("https://x.com/tin/mot-bai-viet-bat-ky")[1] < 1  # plain content page: low, not zero
    assert classify_url("not a url")[1] <= 0.5
    assert url_shape("https://x.com/tin/bai-viet-co-slug-rat-dai-12345") == "/tin/*"
    assert url_shape("https://x.com/users/12345/orders/9") == "/users/*/orders"
    assert url_shape("https://x.com/service/course/getcoursedetail?id=1") == "/service/course/getcoursedetail"


def ingest_fixture(settings, extra_all=""):
    db, _, result = environment(settings, ["vuihoc.vn"])
    plan = ReconOrchestrator(settings, db).build(result.scan_id)
    out = plan.commands[0].output
    gau = ["https://vuihoc.vn/tin/bai-viet-so-mot-rat-dai-dong", "https://vuihoc.vn/tin/bai-viet-so-hai-rat-dai-dong",
           "https://vuihoc.vn/api/v1/users?id=3", "https://vuihoc.vn/login?next=/home", "https://vuihoc.vn/img/a.png",
           "https://other.example.org/x", "https://other.example.org/y", "https://cdn.evil.test/z.js"]
    katana = ["https://vuihoc.vn/admin/panel", "https://vuihoc.vn/api/v1/users?id=3"]
    write_output(out, "subdomains/all.txt", "vuihoc.vn\n")
    write_output(out, "urls/gau.txt", "\n".join(gau) + "\n")
    write_output(out, "urls/katana.txt", "\n".join(katana) + "\n")
    write_output(out, "urls/all.txt", "\n".join(sorted(set(gau + katana))) + "\n" + extra_all)
    stats = Ingester(settings, db).ingest(plan)
    return db, result, stats


def test_tc_url_2_funnel_counts_what_the_scope_gate_kept_and_dropped(settings):
    _, _, stats = ingest_fixture(settings)
    funnel = stats["url_funnel"]
    assert funnel["raw"] == 9 and funnel["in_scope"] == 6 and funnel["out_of_scope"] == 3 and funnel["invalid"] == 0
    assert {h["host"]: h["count"] for h in funnel["out_of_scope_hosts"]} == {"other.example.org": 2, "cdn.evil.test": 1}
    assert funnel["by_verification"] == {"historical": 4, "observed": 2}
    assert funnel["by_tag"]["api"] == 1 and funnel["by_tag"]["admin"] == 1
    assert stats["urls"] == 6  # only in-scope URLs are stored


def test_historical_urls_are_never_labelled_live_and_katana_ones_are_observed(settings):
    db, _, _ = ingest_fixture(settings)
    with db.connect() as conn:
        rows = {r["url"]: r for r in conn.execute("SELECT * FROM url")}
    assert rows["https://vuihoc.vn/login?next=/home"]["verification"] == "historical"
    assert rows["https://vuihoc.vn/login?next=/home"]["source"] == "gau"
    assert rows["https://vuihoc.vn/admin/panel"]["verification"] == "observed"
    assert rows["https://vuihoc.vn/api/v1/users?id=3"]["source"] == "katana"  # seen by both: the stronger evidence wins
    assert not any(r["verification"] == "live" for r in rows.values())


def test_tc_url_3_api_filters_pagination_summary_and_export(settings):
    db, result, stats = ingest_fixture(settings)
    with db.connect() as conn, conn:  # what the runner persists after a scan
        old = json.loads(conn.execute("SELECT stats_json FROM scan_run").fetchone()[0])
        conn.execute("UPDATE scan_run SET status='done',stats_json=?", (json.dumps({**old, **{k: v for k, v in stats.items() if k != "observations"}}),))
    with TestClient(create_app(settings)) as client:
        base = f"/api/programs/{result.slug}"
        everything = client.get(base + "/urls")
        body = everything.json()
        assert everything.headers["x-total-count"] == "5"  # static png hidden by default
        assert body[0]["score"] >= body[-1]["score"] and "api" in body[0]["tags"]
        assert client.get(base + "/urls?include_static=true").headers["x-total-count"] == "6"
        assert client.get(base + "/urls?tag=api").headers["x-total-count"] == "1"
        assert client.get(base + "/urls?verification=observed").headers["x-total-count"] == "2"
        assert client.get(base + "/urls?q=login").json()[0]["url"].endswith("/login?next=/home")
        assert len(client.get(base + "/urls?limit=2&offset=1").json()) == 2
        assert client.get(base + "/urls?host=vuihoc.vn&min_score=3").headers["x-total-count"] != "0"
        assert client.get(base + "/urls?verification=live").json() == []  # nothing is claimed live
        summary = client.get(base + "/urls/summary").json()
        assert summary["total"] == 6 and summary["funnel"]["out_of_scope"] == 3
        news = next(s for s in summary["top_shapes"] if s["shape"] == "/tin/*")
        assert news["count"] == 2 and news["example"].startswith("https://vuihoc.vn/tin/")
        assert summary["by_tag"]["api"] == 1
        text = client.get(base + "/urls/export?tag=api")
        assert text.text.strip() == "https://vuihoc.vn/api/v1/users?id=3"
        assert "attachment" in text.headers["content-disposition"]
        assert client.get(base + "/urls?scan=all&shape=/tin/*").headers["x-total-count"] == "2"
