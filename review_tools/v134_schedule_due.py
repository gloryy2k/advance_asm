"""Advance only the QA localhost schedule after its container has been stopped."""
import json
import sqlite3
import sys

database = sqlite3.connect(sys.argv[1])
database.execute("BEGIN IMMEDIATE")
enabled = database.execute("""SELECT s.id,p.slug,s.enabled FROM schedule s
    JOIN program p ON p.id=s.program_id WHERE s.enabled=1""").fetchall()
assert len(enabled) == 1 and enabled[0][1] == "qa-v134-end2end-local", enabled
database.execute("UPDATE schedule SET next_run_at=? WHERE id=?",
                 ("2026-01-01T00:00:00+00:00", enabled[0][0]))
database.commit()
print(json.dumps({"id": enabled[0][0], "slug": enabled[0][1], "due": "2026-01-01T00:00:00+00:00"}))
