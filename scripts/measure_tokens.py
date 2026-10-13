"""Reproducible offline fixture comparison, not a real-program savings claim."""
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tiktoken
from backend.asm.diff_engine import DiffEngine
from backend.asm.ranking import rank_program
from backend.brief.generator import BriefGenerator
from backend.config import Settings
from backend.db import Database
from backend.jobs.ingest import Ingester
from backend.jobs.recon_orch import ReconOrchestrator
from backend.jobs.scope_resolver import ScopeResolver
from backend.models import ResolveRequest


def main():
    encoding = tiktoken.get_encoding("cl100k_base")
    with tempfile.TemporaryDirectory(prefix="bbasm-token-fixture-") as directory:
        root = Path(directory)
        settings = Settings(_env_file=None, BBASM_DATA=root / "data", BBASM_TARGETS=root / "targets")
        db = Database(settings.BBASM_DATA / "bbasm.db")
        db.migrate()
        result = ScopeResolver(settings, db).resolve(ResolveRequest(input="raw", scope=["*.example.invalid"]))
        plan = ReconOrchestrator(settings, db).build(result.scan_id)
        output = plan.commands[0].output
        corpus = {
            "subdomains/all.txt": "\n".join(f"api{i}.example.invalid" for i in range(30)),
            "live/httpx_full.txt": "\n".join(f"https://api{i}.example.invalid [200] [API service {i}] [GraphQL,nginx]" for i in range(30)),
            "urls/all.txt": "\n".join(f"https://api{i % 30}.example.invalid/v1/resource/{i}?page=1" for i in range(2000)),
            "nuclei/findings.jsonl": "\n".join(json.dumps({"template-id": f"fixture-{i}", "matched-at": f"https://api{i}.example.invalid", "info": {"severity": "medium"}}) for i in range(5)),
        }
        for filename, content in corpus.items():
            path = output / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content + "\n", encoding="utf-8", newline="\n")
        diff = DiffEngine(db)
        diff.capture(plan)
        stats = Ingester(settings, db).ingest(plan)
        diff.apply(plan, stats["observations"], complete=True)
        rank_program(db, plan.program_id, plan.scan_id)
        with db.connect() as conn, conn:
            prior = json.loads(conn.execute("SELECT stats_json FROM scan_run WHERE id=?", (plan.scan_id,)).fetchone()[0])
            prior.update(stats)
            conn.execute("UPDATE scan_run SET status='done',stats_json=? WHERE id=?", (json.dumps(prior), plan.scan_id))
        gen = BriefGenerator(settings, db)
        gen.generate(plan.slug)
        target = gen.target(plan.slug)
        old_text = "\n".join(corpus.values()) + (target / ".scope").read_text(encoding="utf-8") + (target / "PROGRAM.md").read_text(encoding="utf-8")
        new_text = "\n".join((target / f).read_text(encoding="utf-8") for f in ("CLAUDE.md", "PROGRAM.md", "AGENT_BRIEF.md"))
        old, new = len(encoding.encode(old_text)), len(encoding.encode(new_text))
        print(json.dumps({"scenario": "Synthetic offline fixture: 30 hosts, 2000 URLs, 5 nuclei findings",
                          "tokenizer": "cl100k_base", "old_flow": "All fixture recon + scope + PROGRAM.md",
                          "new_flow": "CLAUDE.md + PROGRAM.md + AGENT_BRIEF.md", "old_tokens": old,
                          "new_tokens": new, "reduction_percent": round(100 * (1 - new / old), 2),
                          "brief_bytes": (target / "AGENT_BRIEF.md").stat().st_size,
                          "limitation": "Fixture-only input tokens; no real target, LLM run or universal savings claim"}, indent=2))


if __name__ == "__main__":
    main()
