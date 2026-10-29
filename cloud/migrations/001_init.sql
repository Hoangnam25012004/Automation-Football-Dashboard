-- Lược đồ ban đầu (design doc cloud §6). Bất biến nằm trong schema: CHECK, UNIQUE, FK, index một phần.
CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  pw_hash BLOB NOT NULL,
  pw_salt BLOB NOT NULL,
  role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'disabled')),
  email_verified_at TEXT,
  created_at TEXT NOT NULL,
  last_login_at TEXT,
  daily_crawl_quota INTEGER CHECK (daily_crawl_quota IS NULL OR daily_crawl_quota >= 0)
);

CREATE TABLE sessions (
  id TEXT PRIMARY KEY,                          -- SHA-256 của token; token thật chỉ nằm trong cookie
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  csrf TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  ip TEXT,
  ua TEXT
);
CREATE INDEX sessions_user ON sessions(user_id);

CREATE TABLE email_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose TEXT NOT NULL CHECK (purpose IN ('verify', 'reset')),
  expires_at TEXT NOT NULL,
  used_at TEXT
);
CREATE INDEX email_tokens_user ON email_tokens(user_id);

CREATE TABLE matches (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  match_key TEXT NOT NULL,
  source_url TEXT NOT NULL,
  home TEXT, away TEXT, score TEXT, competition TEXT, kickoff TEXT,
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  refreshed_at TEXT NOT NULL,
  share_token TEXT UNIQUE,                      -- NULL = không có link công khai
  UNIQUE (source, match_key)
);
CREATE INDEX matches_refreshed ON matches(refreshed_at);

CREATE TABLE match_results (
  id INTEGER PRIMARY KEY,
  match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  schema_version INTEGER NOT NULL,
  result_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);
CREATE INDEX match_results_match ON match_results(match_id, id);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  match_key TEXT NOT NULL,
  url TEXT NOT NULL,
  requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  cached INTEGER NOT NULL DEFAULT 0 CHECK (cached IN (0, 1)),   -- 1 = phục vụ từ thư viện, không tốn hạn mức
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'error')),
  attempts INTEGER NOT NULL DEFAULT 0,
  progress_json TEXT,
  error_json TEXT,
  created_at TEXT NOT NULL,
  created_ts REAL NOT NULL,                     -- epoch, để đếm hạn mức theo cửa sổ thời gian
  started_at TEXT,
  started_ts REAL,
  finished_at TEXT
);
-- Khử trùng lặp: mỗi trận chỉ có tối đa 1 job đang chờ/chạy
CREATE UNIQUE INDEX jobs_active ON jobs(source, match_key) WHERE status IN ('queued', 'running');
CREATE INDEX jobs_status ON jobs(status, created_ts);
CREATE INDEX jobs_user ON jobs(requested_by, created_ts);

CREATE TABLE rate_events (
  id INTEGER PRIMARY KEY,
  bucket TEXT NOT NULL,
  key TEXT NOT NULL,
  ts REAL NOT NULL
);
CREATE INDEX rate_events_lookup ON rate_events(bucket, key, ts);

CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,
  user_id INTEGER,
  action TEXT NOT NULL,
  detail TEXT
);
CREATE INDEX audit_log_at ON audit_log(at);
