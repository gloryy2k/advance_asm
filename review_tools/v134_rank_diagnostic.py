"""Read-only SQLite plan/counts for the observed Strong post-processing delay."""
import json
import sqlite3
import sys

uri = "file:" + sys.argv[1].replace("\\", "/") + "?mode=ro"
db = sqlite3.connect(uri, uri=True)
program_id = db.execute("SELECT id FROM program WHERE slug='wolt'").fetchone()[0]
data = {
    "wolt_assets": db.execute("SELECT count(*) FROM asset WHERE program_id=?", (program_id,)).fetchone()[0],
    "wolt_urls": db.execute("SELECT count(*) FROM url WHERE program_id=?", (program_id,)).fetchone()[0],
    "url_indexes": [r[1] for r in db.execute("PRAGMA index_list(url)")],
    "finding_indexes": [r[1] for r in db.execute("PRAGMA index_list(finding)")],
    "url_lookup_plan": [r[3] for r in db.execute("EXPLAIN QUERY PLAN SELECT url FROM url WHERE asset_id=1 AND last_seen_scan=64")],
    "finding_lookup_plan": [r[3] for r in db.execute("EXPLAIN QUERY PLAN SELECT severity FROM finding WHERE asset_id=1 AND type='nuclei' AND last_seen_scan=64")],
}
print(json.dumps(data, ensure_ascii=True))
