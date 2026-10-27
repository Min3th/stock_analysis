import fs from "node:fs";
import path from "node:path";
import Database from "better-sqlite3";

export type Db = Database.Database;

/**
 * The SQLite file is an index of runs, jobs, uploads and submitted corrections.
 * It never holds financial values: those stay in the Python run directories
 * (`data/runs/<run_id>/*.json`), which the API reads as they are.
 */
export const SCHEMA = `
CREATE TABLE IF NOT EXISTS runs (
  id            TEXT PRIMARY KEY,
  sector        TEXT NOT NULL,
  period        TEXT NOT NULL,
  ticker        TEXT,
  offline       INTEGER NOT NULL DEFAULT 0,
  status        TEXT NOT NULL CHECK (status IN ('queued','running','ok','empty','failed')),
  run_dir       TEXT NOT NULL,
  git_commit    TEXT,
  config_hash   TEXT,
  counts_json   TEXT,
  error         TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,
  run_id        TEXT REFERENCES runs(id),
  status        TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
  args_json     TEXT NOT NULL,
  log_path      TEXT,
  exit_code     INTEGER,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);

CREATE TABLE IF NOT EXISTS uploads (
  id               TEXT PRIMARY KEY,
  ticker           TEXT NOT NULL,
  kind             TEXT NOT NULL CHECK (kind IN ('annual_report','interim_statement')),
  period_end       TEXT NOT NULL,
  period_months    INTEGER,
  original_filename TEXT NOT NULL,
  sha256           TEXT NOT NULL,
  stored_path      TEXT NOT NULL,
  status           TEXT NOT NULL CHECK (status IN ('pending','accepted','rejected')),
  preview_json     TEXT,
  created_at       TEXT NOT NULL,
  decided_at       TEXT
);

CREATE TABLE IF NOT EXISTS corrections_log (
  id             TEXT PRIMARY KEY,
  correction_id  TEXT,
  ticker         TEXT NOT NULL,
  metric         TEXT NOT NULL,
  payload_json   TEXT NOT NULL,
  created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS runs_created ON runs (created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs (status, created_at);
CREATE INDEX IF NOT EXISTS uploads_status ON uploads (status, created_at);
`;

export function openDb(file: string): Db {
  if (file !== ":memory:") {
    fs.mkdirSync(path.dirname(file), { recursive: true });
  }
  const db = new Database(file);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  db.exec(SCHEMA);
  return db;
}
