-- Users, roles, audit log for the team web UI. The core generation engine
-- (engine.py/store.py/accounts.json/tasks.json) does not touch these tables.

CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_log (
    id       BIGSERIAL PRIMARY KEY,
    ts       TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id  BIGINT REFERENCES users(id) ON DELETE SET NULL,
    username TEXT,            -- denormalized snapshot, survives user deletion
    action   TEXT NOT NULL,   -- 'login', 'login_failed', 'account_add', 'task_submit', ...
    target   TEXT,            -- e.g. account id, task id, affected username
    detail   JSONB,
    ip       TEXT
);
CREATE INDEX IF NOT EXISTS audit_log_ts_idx ON audit_log (ts DESC);

-- Tracks which numbered migration files have already run (db.run_migrations).
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
