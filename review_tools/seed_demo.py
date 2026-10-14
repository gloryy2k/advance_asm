"""Review harness: fill a data dir with a realistic finished program ("demo-shop") — two completed scans,
URLs from archive + crawl (some out of scope), a nuclei finding, ranked assets, brief — no network, no tools.
Used by mock_h1_server.py so screenshots/E2E show real-looking results."""
import json

from backend.asm.diff_engine import DiffEngine
from backend.asm.ranking import rank_program
from backend.brief.generator import BriefGenerator
from backend.jobs.ingest import Ingester
from backend.jobs.recon_orch import ReconOrchestrator
from backend.jobs.scope_resolver import ScopeResolver
from backend.models import ResolveRequest
from backend.asm.monitors import Monitors


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def finish(settings, database, scan_id, files, depth, missing):
    from backend.jobs.runner import store_config
    plan = ReconOrchestrator(settings, database).build(scan_id)
    with database.connect() as conn, conn:
        conn.execute("UPDATE scan_run SET status='running',started_at='2026-10-14T08:00:00.000Z' WHERE id=?", (scan_id,))
        conn.execute("UPDATE scan_config SET depth=? WHERE scan_run_id=?", (depth, scan_id))
        conn.execute("UPDATE scan_run SET depth=? WHERE id=?", (depth, scan_id))
    engine = DiffEngine(database)
    engine.capture(plan)
    out = plan.commands[0].output
    for relative, text in files.items():
        write(out / relative, text)
    stats = Ingester(settings, database).ingest(plan)
    stats["missing_tools"] = missing
    stats["diff"] = engine.apply(plan, stats["observations"], complete=True)
    rank_program(database, plan.program_id, scan_id)
    with database.connect() as conn, conn:
        old = json.loads(conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (scan_id,)).fetchone()[0])
        conn.execute("UPDATE scan_run SET status='done',finished_at='2026-10-14T08:04:10.000Z',stats_json=? WHERE id=?",
                     (json.dumps({**old, **stats}), scan_id))
    BriefGenerator(settings, database).generate(plan.slug, scan_id)


def seed(settings, database):
    database.migrate()
    resolver = ScopeResolver(settings, database)
    first = resolver.resolve(ResolveRequest(input="raw", name="demo-shop", scope=["shop.example.com", "*.example.com"], scope_out=["admin.example.com"],
                                            policy_text="Automated scanning allowed up to 10 req/s. Do not test /internal/."))
    gau = [f"https://shop.example.com/product/{n}-ten-san-pham-dai-{n}" for n in range(1, 40)] + [
        "https://shop.example.com/api/v1/users?id=12", "https://shop.example.com/api/v1/orders?order_id=9", "https://shop.example.com/login?next=/account",
        "https://shop.example.com/.env.bak", "https://shop.example.com/assets/app.min.js", "https://shop.example.com/img/logo.png",
        "https://shop.example.com/redirect?url=https://evil.test", "https://shop.example.com/download?file=report.pdf",
        "https://cdn.thirdparty.test/lib.js", "https://cdn.thirdparty.test/x.js", "https://other.org/page"]
    hosts = "shop.example.com\nwww.example.com\napi.example.com\n"
    files1 = {"subdomains/all.txt": hosts, "urls/gau.txt": "\n".join(gau) + "\n", "urls/all.txt": "\n".join(gau) + "\n",
              "urls/js_files.txt": "https://shop.example.com/assets/app.min.js\n", "params/unique_params.txt": "id\norder_id\nurl\nfile\nnext\n"}
    finish(settings, database, first.scan_id, files1, "passive", ["katana", "nuclei"])
    second = resolver.resolve(ResolveRequest(input="raw", name="demo-shop", scope=["shop.example.com", "*.example.com"], scope_out=["admin.example.com"]))
    katana = ["https://shop.example.com/admin/panel", "https://shop.example.com/api/v1/users?id=12", "https://shop.example.com/api/v2/search?q=a"]
    files2 = {**files1, "subdomains/all.txt": hosts + "staging.example.com\n", "urls/katana.txt": "\n".join(katana) + "\n",
              "urls/all.txt": "\n".join(sorted(set(gau + katana))) + "\n",
              "live/urls.txt": "https://shop.example.com\nhttps://api.example.com\n",
              "live/httpx_full.txt": "https://shop.example.com [200] [5120] [Demo Shop] [nginx,PHP,jQuery]\nhttps://api.example.com [403] [20] [Forbidden] [nginx,GraphQL]\nhttps://staging.example.com [200] [900] [Staging] [Express]\n",
              "nuclei/findings.jsonl": json.dumps({"template-id": "exposed-env", "matched-at": "https://shop.example.com/.env", "info": {"severity": "medium", "name": "Exposed .env"}}) + "\n",
              "js/endpoints.txt": "/api/v2/cart\n/api/v2/checkout\n"}
    finish(settings, database, second.scan_id, files2, "light", ["nmap", "ffuf"])
    # a fresh draft so Portfolio shows the "waiting for review" row too
    resolver.resolve(ResolveRequest(input="raw", name="demo-draft", scope=["draft.example.org"]))
