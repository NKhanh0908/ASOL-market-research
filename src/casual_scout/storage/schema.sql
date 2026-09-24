PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS markets (
    country TEXT PRIMARY KEY CHECK (country = lower(country) AND length(country) = 2),
    name TEXT NOT NULL,
    market_group TEXT NOT NULL CHECK (market_group IN ('ASEAN', 'US')),
    source_status TEXT NOT NULL CHECK (source_status IN ('verified', 'unverified')),
    source_note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS charts (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    platform TEXT NOT NULL,
    country TEXT NOT NULL REFERENCES markets(country),
    collection TEXT NOT NULL,
    genre TEXT NOT NULL,
    depth INTEGER NOT NULL CHECK (depth > 0),
    version INTEGER NOT NULL CHECK (version > 0),
    endpoint TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS chart_identity
ON charts(provider, platform, country, collection, genre, depth, version);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    "trigger" TEXT NOT NULL CHECK ("trigger" IN ('manual', 'survey', 'daily')),
    status TEXT NOT NULL CHECK (
        status IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'interrupted')
    ),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    summary_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS daily_schedule (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    time_local TEXT NOT NULL DEFAULT '07:00' CHECK (time_local = '07:00'),
    timezone TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    country TEXT NOT NULL DEFAULT 'vn' REFERENCES markets(country),
    chart_type TEXT NOT NULL DEFAULT 'top-free' CHECK (chart_type = 'top-free'),
    last_triggered_local_date TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS one_time_collection_schedule (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    scheduled_for_utc TEXT,
    scheduled_for_local TEXT,
    status TEXT NOT NULL DEFAULT 'empty' CHECK (
        status IN ('empty', 'pending', 'triggered', 'missed')
    ),
    run_id TEXT REFERENCES runs(id),
    created_at TEXT,
    triggered_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_runs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    chart_id TEXT NOT NULL REFERENCES charts(id),
    chart_status TEXT NOT NULL CHECK (
        chart_status IN ('pending', 'complete', 'partial', 'failed')
    ),
    enrichment_status TEXT NOT NULL CHECK (
        enrichment_status IN ('pending', 'complete', 'partial', 'failed', 'not_requested')
    ),
    error TEXT,
    received_count INTEGER NOT NULL DEFAULT 0 CHECK (received_count >= 0),
    valid_count INTEGER NOT NULL DEFAULT 0 CHECK (valid_count >= 0),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    UNIQUE (run_id, chart_id)
);

CREATE TABLE IF NOT EXISTS collector_lock (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    run_id TEXT NOT NULL REFERENCES runs(id),
    pid INTEGER NOT NULL,
    process_created_at REAL NOT NULL,
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS survey_slots (
    slot_utc TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('pending', 'observed', 'missed')),
    run_id TEXT REFERENCES runs(id),
    recorded_at TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS raw_responses (
    hash TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    status INTEGER,
    received_at TEXT NOT NULL,
    headers_json TEXT NOT NULL,
    error TEXT,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0)
);

CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    market_run_id TEXT NOT NULL REFERENCES market_runs(id),
    raw_hash TEXT NOT NULL REFERENCES raw_responses(hash),
    observed_at TEXT NOT NULL,
    source_updated TEXT,
    quality TEXT NOT NULL CHECK (quality IN ('complete', 'partial', 'invalid')),
    issues_json TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS snapshot_per_market_run
ON snapshots(market_run_id);

CREATE TABLE IF NOT EXISTS apps (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    platform TEXT NOT NULL,
    source_app_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (provider, platform, source_app_id)
);

CREATE TABLE IF NOT EXISTS entries (
    snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
    app_ref TEXT NOT NULL REFERENCES apps(id),
    app_id TEXT NOT NULL,
    rank INTEGER NOT NULL CHECK (rank > 0),
    name TEXT NOT NULL,
    store_url TEXT NOT NULL,
    icon_url TEXT,
    developer TEXT,
    source_genres_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, app_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS entry_app
ON entries(snapshot_id, app_id);

CREATE UNIQUE INDEX IF NOT EXISTS entry_rank
ON entries(snapshot_id, rank);

CREATE TABLE IF NOT EXISTS metadata_versions (
    id TEXT PRIMARY KEY,
    app_ref TEXT NOT NULL REFERENCES apps(id),
    provider TEXT NOT NULL,
    platform TEXT NOT NULL,
    country TEXT NOT NULL REFERENCES markets(country),
    app_id TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('complete', 'partial', 'failed')),
    raw_hash TEXT NOT NULL REFERENCES raw_responses(hash),
    name TEXT,
    developer TEXT,
    primary_genre TEXT,
    genres_json TEXT NOT NULL,
    description TEXT,
    average_rating REAL,
    rating_count INTEGER,
    store_url TEXT,
    price REAL,
    currency TEXT,
    in_app_purchases_json TEXT DEFAULT '[]',
    has_in_app_purchases INTEGER DEFAULT 0,
    monetization_model TEXT DEFAULT 'UNKNOWN',
    values_json TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS metadata_version_identity
ON metadata_versions(provider, platform, country, app_id, fetched_at, raw_hash);

CREATE TABLE IF NOT EXISTS snapshot_metadata (
    snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
    app_id TEXT NOT NULL,
    metadata_version_id TEXT NOT NULL REFERENCES metadata_versions(id),
    PRIMARY KEY (snapshot_id, app_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS snapshot_metadata_once
ON snapshot_metadata(snapshot_id, app_id);

CREATE TABLE IF NOT EXISTS request_observations (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id),
    market_run_id TEXT REFERENCES market_runs(id),
    endpoint TEXT NOT NULL,
    started_at TEXT NOT NULL,
    elapsed_ms INTEGER NOT NULL CHECK (elapsed_ms >= 0),
    status INTEGER,
    error TEXT,
    retry_index INTEGER NOT NULL CHECK (retry_index > 0),
    response_bytes INTEGER NOT NULL CHECK (response_bytes >= 0),
    source_timestamp TEXT,
    raw_hash TEXT REFERENCES raw_responses(hash)
);

CREATE TRIGGER IF NOT EXISTS snapshots_are_immutable_update
BEFORE UPDATE ON snapshots
BEGIN
    SELECT RAISE(ABORT, 'snapshots are immutable');
END;

CREATE TRIGGER IF NOT EXISTS snapshots_are_immutable_delete
BEFORE DELETE ON snapshots
BEGIN
    SELECT RAISE(ABORT, 'snapshots are immutable');
END;

CREATE TRIGGER IF NOT EXISTS entries_are_immutable_update
BEFORE UPDATE ON entries
BEGIN
    SELECT RAISE(ABORT, 'snapshot entries are immutable');
END;

CREATE TRIGGER IF NOT EXISTS entries_are_immutable_delete
BEFORE DELETE ON entries
BEGIN
    SELECT RAISE(ABORT, 'snapshot entries are immutable');
END;

CREATE TRIGGER IF NOT EXISTS metadata_versions_are_immutable_update
BEFORE UPDATE ON metadata_versions
BEGIN
    SELECT RAISE(ABORT, 'metadata versions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS metadata_versions_are_immutable_delete
BEFORE DELETE ON metadata_versions
BEGIN
    SELECT RAISE(ABORT, 'metadata versions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS snapshot_metadata_is_immutable_update
BEFORE UPDATE ON snapshot_metadata
BEGIN
    SELECT RAISE(ABORT, 'snapshot metadata bindings are immutable');
END;

CREATE TRIGGER IF NOT EXISTS snapshot_metadata_is_immutable_delete
BEFORE DELETE ON snapshot_metadata
BEGIN
    SELECT RAISE(ABORT, 'snapshot metadata bindings are immutable');
END;

CREATE TRIGGER IF NOT EXISTS snapshot_metadata_requires_open_run
BEFORE INSERT ON snapshot_metadata
WHEN (
    SELECT runs.status
    FROM snapshots
    JOIN market_runs ON market_runs.id = snapshots.market_run_id
    JOIN runs ON runs.id = market_runs.run_id
    WHERE snapshots.id = NEW.snapshot_id
) NOT IN ('queued', 'running')
BEGIN
    SELECT RAISE(ABORT, 'cannot bind metadata to a closed run');
END;

CREATE TABLE IF NOT EXISTS daily_canonical_snapshots (
    date TEXT NOT NULL,
    country TEXT NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (date, country)
);

CREATE TABLE IF NOT EXISTS daily_rank_analytics (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    country TEXT NOT NULL,
    app_id TEXT NOT NULL,
    current_rank INTEGER NOT NULL,
    rank_1d_ago INTEGER,
    delta_1d INTEGER,
    rank_3d_ago INTEGER,
    delta_3d INTEGER,
    rank_7d_ago INTEGER,
    delta_7d INTEGER,
    signal TEXT NOT NULL,
    signal_reasons_json TEXT NOT NULL,
    subgenre TEXT,
    mechanic TEXT NOT NULL,
    mechanic_evidence TEXT,
    mechanic_confidence TEXT NOT NULL,
    cross_market_count INTEGER NOT NULL,
    cross_markets_json TEXT NOT NULL,
    grossing_rank INTEGER,
    free_rank INTEGER,
    monetization_model TEXT NOT NULL DEFAULT 'PURE_ADS',
    monetization_efficiency_flag TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(date, country, app_id)
);

CREATE INDEX IF NOT EXISTS idx_analytics_date_country ON daily_rank_analytics(date, country);
CREATE INDEX IF NOT EXISTS idx_analytics_signal ON daily_rank_analytics(date, signal);
CREATE INDEX IF NOT EXISTS idx_analytics_app ON daily_rank_analytics(app_id);

CREATE TABLE IF NOT EXISTS shortlists (
    id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL,
    title TEXT NOT NULL,
    icon_url TEXT,
    developer TEXT,
    subgenre TEXT,
    mechanic TEXT,
    primary_country TEXT NOT NULL,
    rank_at_bookmark INTEGER NOT NULL,
    opportunity_score REAL,
    status TEXT NOT NULL DEFAULT 'CONSIDERING',
    priority TEXT NOT NULL DEFAULT 'MEDIUM',
    notes TEXT,
    tags TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(app_id)
);

CREATE INDEX IF NOT EXISTS idx_shortlist_status ON shortlists(status);
CREATE INDEX IF NOT EXISTS idx_shortlist_priority ON shortlists(priority);
CREATE INDEX IF NOT EXISTS idx_shortlist_app ON shortlists(app_id);
