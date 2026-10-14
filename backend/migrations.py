"""Ordered schema migrations. schema.sql is the frozen v1 baseline; every later change lives here.

Rules: only additive changes (ADD COLUMN / CREATE ...), one transaction per version, never edit a
released migration. A fresh database runs the baseline and then every migration, so there is a
single upgrade path and it is exercised by every test that creates a database.
"""

MIGRATIONS: dict[int, list[str]] = {
    2: [
        # URL inventory: classification and evidence level of every stored URL.
        "ALTER TABLE url ADD COLUMN tags_json TEXT",
        "ALTER TABLE url ADD COLUMN score REAL",
        "ALTER TABLE url ADD COLUMN verification TEXT",
        "ALTER TABLE url ADD COLUMN status_code INTEGER",
        "ALTER TABLE url ADD COLUMN shape TEXT",
        "CREATE INDEX idx_url_prog_score ON url(program_id, score DESC)",
        "CREATE INDEX idx_url_prog_shape ON url(program_id, shape)",
        # Diff compares against a *named* completed scan, not mutable asset rows.
        "ALTER TABLE scan_run ADD COLUMN baseline_scan_id INTEGER",
        # Per-scan custom options beyond the fixed columns (profiles, per-tool switches).
        "ALTER TABLE scan_config ADD COLUMN options_json TEXT",
        # User-defined presets.
        """CREATE TABLE profile (
            id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, description TEXT,
            based_on TEXT, config_json TEXT NOT NULL, created_at TEXT, updated_at TEXT
        )""",
        "ALTER TABLE program ADD COLUMN default_profile_id INTEGER",
    ],
}
SCHEMA_VERSION = max(MIGRATIONS)


def _backfill_urls(conn):
    """URLs stored by v1 have no tags/score/shape. Classify them now so the inventory is usable right after
    the upgrade. Verification stays 'historical': we cannot know how a v1 URL was learned, and never claiming
    'observed' is the safe direction."""
    from backend.asm.urlintel import classify_url, url_shape
    import json
    rows = conn.execute("SELECT id,url FROM url WHERE tags_json IS NULL").fetchall()
    for start in range(0, len(rows), 5000):
        conn.executemany(
            "UPDATE url SET tags_json=?,score=?,shape=?,verification=COALESCE(verification,'historical') WHERE id=?",
            [(json.dumps(tags), score, url_shape(url), row_id)
             for row_id, url in rows[start:start + 5000] for tags, score in [classify_url(url)]])


# Python steps that run in the same transaction right after a version's SQL statements.
AFTER: dict = {2: _backfill_urls}
