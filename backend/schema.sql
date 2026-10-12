CREATE TABLE schema_meta (version INTEGER);
CREATE TABLE program (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL, source TEXT NOT NULL,
    handle TEXT, platform TEXT DEFAULT 'h1', policy_json TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE scope_rule (
    id INTEGER PRIMARY KEY, program_id INTEGER REFERENCES program(id),
    pattern TEXT NOT NULL, kind TEXT NOT NULL, asset_type TEXT
);
CREATE TABLE scan_run (
    id INTEGER PRIMARY KEY, program_id INTEGER REFERENCES program(id),
    depth TEXT NOT NULL, status TEXT NOT NULL, trigger TEXT DEFAULT 'manual',
    started_at TEXT, finished_at TEXT, error TEXT, stats_json TEXT
);
CREATE TABLE asset (
    id INTEGER PRIMARY KEY, program_id INTEGER REFERENCES program(id),
    host TEXT NOT NULL, ip TEXT, status_code INTEGER, title TEXT, tech_json TEXT,
    category TEXT, first_seen_scan INTEGER, last_seen_scan INTEGER, state TEXT,
    rank_score REAL, rank_reasons_json TEXT, UNIQUE(program_id, host)
);
CREATE INDEX idx_asset_prog_rank ON asset(program_id, rank_score DESC);
CREATE TABLE url (
    id INTEGER PRIMARY KEY, program_id INTEGER, asset_id INTEGER,
    url TEXT NOT NULL, source TEXT, first_seen_scan INTEGER, last_seen_scan INTEGER,
    UNIQUE(program_id, url)
);
CREATE TABLE finding (
    id INTEGER PRIMARY KEY, program_id INTEGER, asset_id INTEGER,
    type TEXT, severity TEXT, name TEXT, detail_json TEXT,
    first_seen_scan INTEGER, last_seen_scan INTEGER,
    UNIQUE(program_id, type, name, asset_id)
);
CREATE TABLE diff_event (
    id INTEGER PRIMARY KEY, program_id INTEGER, scan_run_id INTEGER,
    entity TEXT, entity_ref TEXT, change TEXT, detail_json TEXT, created_at TEXT
);
CREATE INDEX idx_diff_prog_scan ON diff_event(program_id, scan_run_id);
CREATE TABLE schedule (
    id INTEGER PRIMARY KEY, program_id INTEGER UNIQUE REFERENCES program(id),
    interval TEXT NOT NULL, depth TEXT NOT NULL, enabled INTEGER DEFAULT 1,
    config_json TEXT, next_run_at TEXT, created_at TEXT
);
CREATE TABLE scan_config (
    id INTEGER PRIMARY KEY, scan_run_id INTEGER UNIQUE REFERENCES scan_run(id),
    depth TEXT, threads INTEGER, rate_limit INTEGER, scan_timeout INTEGER,
    nuclei_severity TEXT, skip_nmap INTEGER, skip_nuclei INTEGER,
    skip_active_crawl INTEGER, categories_enabled_json TEXT,
    excluded_hosts_json TEXT, created_at TEXT
);
