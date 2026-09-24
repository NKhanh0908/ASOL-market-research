CREATE TABLE IF NOT EXISTS android_jobs (
    id TEXT PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    trigger TEXT NOT NULL CHECK(trigger IN ('manual','daily')),
    status TEXT NOT NULL CHECK(status IN ('pending','queued','running','succeeded','partial','failed','interrupted')),
    local_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    phase TEXT NOT NULL DEFAULT 'pending',
    total INTEGER NOT NULL DEFAULT 0,
    processed INTEGER NOT NULL DEFAULT 0,
    batches INTEGER NOT NULL DEFAULT 0,
    errors_json TEXT NOT NULL DEFAULT '[]',
    pid INTEGER,
    process_created REAL,
    dispatched_at TEXT,
    core_run_id TEXT REFERENCES runs(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS android_daily_once ON android_jobs(local_date)
    WHERE trigger='daily';
CREATE TABLE IF NOT EXISTS android_charts (
    job_id TEXT NOT NULL REFERENCES android_jobs(id),
    feed TEXT NOT NULL CHECK(feed IN ('top-free','top-grossing')),
    observed_at TEXT NOT NULL,
    count INTEGER NOT NULL,
    evidence TEXT NOT NULL,
    PRIMARY KEY(job_id,feed)
);
CREATE TABLE IF NOT EXISTS android_entries (
    job_id TEXT NOT NULL REFERENCES android_jobs(id),
    package TEXT NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY(job_id,package)
);
CREATE TABLE IF NOT EXISTS android_schedule (
    id INTEGER PRIMARY KEY CHECK(id=1),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
    last_date TEXT
);
INSERT OR IGNORE INTO android_schedule(id) VALUES(1);
