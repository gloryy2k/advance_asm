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
        "CREATE INDEX idx_url_prog_score ON url(program_id, score DESC)",
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
