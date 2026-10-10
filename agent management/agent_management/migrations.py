"""Forward-only, backed-up migrations for the isolated coordination database."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_lock = threading.RLock()
VERSION = 2
SCHEMA = """
CREATE TABLE IF NOT EXISTS harnesses(id TEXT PRIMARY KEY,spec_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rig_runtime(rig_id TEXT PRIMARY KEY REFERENCES rigs(id),
  enabled INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS seats(rig_id TEXT NOT NULL REFERENCES rigs(id),id TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'IDLE',worktree TEXT,checkpoint TEXT,session_id TEXT,
  PRIMARY KEY(rig_id,id));
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,rig_id TEXT NOT NULL,seat_id TEXT NOT NULL,
  task_id TEXT,request_id TEXT,provider_id TEXT NOT NULL,provider_session TEXT,
  state TEXT NOT NULL,process_id INTEGER,stop_receipt_json TEXT,usage_json TEXT,
  created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_sessions_seat ON sessions(rig_id,seat_id,state);
CREATE TABLE IF NOT EXISTS journal(id INTEGER PRIMARY KEY AUTOINCREMENT,rig_id TEXT,seat_id TEXT,
  task_id TEXT,request_id TEXT,provider_id TEXT,session_id TEXT,kind TEXT NOT NULL,
  data_json TEXT NOT NULL,timestamp TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_journal_rig ON journal(rig_id,id);
CREATE TABLE IF NOT EXISTS permissions(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,
  operation_json TEXT NOT NULL,state TEXT NOT NULL,decision TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY,rig_id TEXT NOT NULL,
  descriptor_json TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,name TEXT NOT NULL,token_hash TEXT NOT NULL UNIQUE,
  scopes_json TEXT NOT NULL,rig_ids_json TEXT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,
  expires_at TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pairings(id TEXT PRIMARY KEY,code_hash TEXT NOT NULL,
  scopes_json TEXT NOT NULL,rig_ids_json TEXT NOT NULL,expires_at TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS outbox(request_id TEXT PRIMARY KEY,rig_id TEXT NOT NULL,
  binding_json TEXT NOT NULL,content_hash TEXT NOT NULL,state TEXT NOT NULL,
  run_id TEXT,receipt_json TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bridge_claims(request_id TEXT PRIMARY KEY,owner TEXT NOT NULL,
  lease_until TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS resources(rig_id TEXT NOT NULL,id TEXT NOT NULL,
  spec_json TEXT NOT NULL,PRIMARY KEY(rig_id,id));
CREATE TABLE IF NOT EXISTS integration_config(id TEXT PRIMARY KEY,spec_json TEXT NOT NULL);
"""


def migrate(path: Path):
    # AgentStore creates the v1 tables first. The backup also includes that baseline.
    with _lock:
        with sqlite3.connect(path, timeout=15) as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version > VERSION:
                raise ValueError("Control database is newer than this application")
            if version == VERSION:
                return
            backup = path.with_name(path.name + f".before-v{VERSION}.bak")
            if not backup.exists():
                if backup.is_symlink():
                    raise ValueError("Refusing symlinked migration backup")
                with sqlite3.connect(backup) as target:
                    con.backup(target)
            con.executescript("BEGIN IMMEDIATE;" + SCHEMA + f"PRAGMA user_version={VERSION};COMMIT;")


def backup_database(path: Path, target: Path):
    if target.exists() or target.is_symlink():
        raise ValueError("Backup target must be a new file")
    with sqlite3.connect(path) as source, sqlite3.connect(target) as dest:
        source.backup(dest)
        if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup integrity check failed")
