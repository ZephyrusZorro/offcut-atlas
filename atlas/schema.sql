CREATE TABLE IF NOT EXISTS meta (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    revision INTEGER NOT NULL CHECK(revision>=0)
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
    revision INTEGER NOT NULL, request TEXT NOT NULL, stocks TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued','running','optimal','feasible','infeasible','unknown','failed')),
    token TEXT, lease_until REAL, attempts INTEGER NOT NULL DEFAULT 0,
    result TEXT, verification TEXT, receipt TEXT, error TEXT,
    request_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS runs_work ON runs(status,lease_until);
CREATE TABLE IF NOT EXISTS rails (
    id TEXT PRIMARY KEY, material TEXT NOT NULL, length_mm INTEGER NOT NULL CHECK(length_mm>0),
    kind TEXT NOT NULL CHECK(kind IN ('remnant','stock')),
    source_run TEXT REFERENCES runs(id), parent_id TEXT REFERENCES rails(id),
    consumed_by TEXT REFERENCES runs(id)
);
CREATE INDEX IF NOT EXISTS rails_available ON rails(consumed_by);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, run_id TEXT REFERENCES runs(id), stage TEXT NOT NULL,
    detail TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_run ON events(run_id,id);
PRAGMA user_version=1;
