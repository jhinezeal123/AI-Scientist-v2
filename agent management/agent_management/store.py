"""Durable coordination store, separated from research-run/approval authority.

This database never writes an AI-Scientist project SQLite database. Dispatch of
research actions remains exclusively owned by existing Planning/Working services.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid


_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS rigs (
  id TEXT PRIMARY KEY, spec_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, rig_id TEXT NOT NULL REFERENCES rigs(id),
  seat TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE,
  content_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
  depends_on TEXT, state TEXT NOT NULL,
  lease_token TEXT, lease_until TEXT, result_json TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_admit ON tasks(rig_id,state,created_at);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, rig_id TEXT NOT NULL REFERENCES rigs(id),
  sender TEXT NOT NULL, recipient TEXT NOT NULL,
  body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inbox ON messages(rig_id,recipient,id);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, rig_id TEXT NOT NULL,
  kind TEXT NOT NULL, ref TEXT NOT NULL, timestamp TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class AgentStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.exists() and self.path.is_symlink():
            raise ValueError("Refusing symlinked control database")

    @contextmanager
    def _connection(self, write: bool = False):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Keep the control-plane separate; do not modify Workbench's project DBs.
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.executescript(_SCHEMA)
            if write:
                con.execute("BEGIN IMMEDIATE")
            yield con
            if write:
                con.commit()
        except BaseException:
            if write:
                con.rollback()
            raise
        finally:
            con.close()

    def create_rig(self, rig_id: str, spec: dict) -> dict:
        if not isinstance(spec, dict) or not isinstance(rig_id, str) or not rig_id:
            raise ValueError("Invalid rig")
        raw = _json(spec)
        with self._connection(write=True) as con:
            existing = con.execute("SELECT spec_json FROM rigs WHERE id=?", (rig_id,)).fetchone()
            if existing:
                if existing["spec_json"] != raw:
                    raise ValueError("Rig ID already exists with a different spec")
            else:
                con.execute("INSERT INTO rigs VALUES(?,?,?)", (rig_id, raw, _now()))
                self._event(con, rig_id, "rig_created", rig_id)
        return {"id": rig_id, "spec": spec}

    @staticmethod
    def _event(con, rig_id: str, kind: str, ref: str):
        con.execute("INSERT INTO events(rig_id,kind,ref,timestamp) VALUES(?,?,?,?)",
                    (rig_id, kind, ref, _now()))

    def enqueue(self, rig_id: str, seat: str, request_id: str, payload: dict,
                *, depends_on: str | None = None) -> dict:
        if not all(isinstance(x, str) and x for x in (rig_id, seat, request_id)):
            raise ValueError("Invalid task identity")
        if not isinstance(payload, dict):
            raise ValueError("Task payload must be a JSON object")
        raw = _json(payload)
        if len(raw.encode("utf-8")) > 128_000:
            raise ValueError("Task metadata exceeds 128KB")
        digest = hashlib.sha256(_json([rig_id, seat, raw, depends_on]).encode()).hexdigest()
        with self._connection(write=True) as con:
            if not con.execute("SELECT 1 FROM rigs WHERE id=?", (rig_id,)).fetchone():
                raise KeyError("Unknown rig")
            old = con.execute("SELECT * FROM tasks WHERE request_id=?", (request_id,)).fetchone()
            if old:
                if old["content_hash"] != digest:
                    raise ValueError("Request ID reused with different task input")
                return self._task(old)
            if depends_on:
                predecessor = con.execute("SELECT rig_id FROM tasks WHERE id=?", (depends_on,)).fetchone()
                if not predecessor or predecessor["rig_id"] != rig_id:
                    raise ValueError("Task dependency must belong to the same rig")
            task_id = uuid.uuid4().hex
            con.execute("""INSERT INTO tasks(id,rig_id,seat,request_id,content_hash,
                        payload_json,depends_on,state,created_at)
                        VALUES(?,?,?,?,?,?,?,'PENDING',?)""",
                        (task_id, rig_id, seat, request_id, digest, raw, depends_on, _now()))
            self._event(con, rig_id, "task_enqueued", task_id)
            return self._task(con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    @staticmethod
    def _task(row) -> dict:
        return {key: row[key] for key in (
            "id", "rig_id", "seat", "request_id", "depends_on", "state", "created_at"
        )}

    def claim(self, rig_id: str, seat: str, *, lease_seconds: int = 300) -> dict | None:
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease duration")
        with self._connection(write=True) as con:
            # A lease that timed out is UNKNOWN, never auto-retried: the harness may still run.
            con.execute("""UPDATE tasks SET state='UNKNOWN'
                           WHERE rig_id=? AND state='LEASED' AND lease_until < ?""",
                        (rig_id, _now()))
            row = con.execute("""SELECT t.* FROM tasks t
                 LEFT JOIN tasks dep ON dep.id=t.depends_on
                 WHERE t.rig_id=? AND t.seat=? AND t.state='PENDING'
                       AND (t.depends_on IS NULL OR dep.state='DONE')
                 ORDER BY t.created_at,t.id LIMIT 1""", (rig_id, seat)).fetchone()
            if row is None:
                return None
            from datetime import timedelta
            until = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat()
            token = uuid.uuid4().hex
            con.execute("UPDATE tasks SET state='LEASED',lease_token=?,lease_until=? WHERE id=?",
                        (token, until, row["id"]))
            self._event(con, rig_id, "task_claimed", row["id"])
            return {**self._task(row), "state": "LEASED", "lease_token": token,
                    "payload": json.loads(row["payload_json"])}

    def finish(self, task_id: str, lease_token: str, *, result: dict | None = None,
               uncertain: bool = False) -> dict:
        if not isinstance(result, (dict, type(None))):
            raise ValueError("Result must be JSON object or null")
        with self._connection(write=True) as con:
            row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError("Unknown task")
            if row["state"] != "LEASED" or row["lease_token"] != lease_token:
                raise ValueError("Lease invalid or task needs reconciliation")
            state = "UNKNOWN" if uncertain else "DONE"
            con.execute("UPDATE tasks SET state=?, result_json=?, lease_token=NULL WHERE id=?",
                        (state, _json(result) if result is not None else None, task_id))
            self._event(con, row["rig_id"], "task_unknown" if uncertain else "task_done", task_id)
            return {**self._task(row), "state": state}

    def send(self, rig_id: str, sender: str, recipient: str, body: str) -> int:
        if not all(isinstance(x, str) and x for x in (rig_id, sender, recipient, body)):
            raise ValueError("Invalid message")
        if len(body) > 20_000:
            raise ValueError("Message exceeds size limit")
        with self._connection(write=True) as con:
            if not con.execute("SELECT 1 FROM rigs WHERE id=?", (rig_id,)).fetchone():
                raise KeyError("Unknown rig")
            cursor = con.execute("INSERT INTO messages(rig_id,sender,recipient,body,created_at) VALUES(?,?,?,?,?)",
                                 (rig_id, sender, recipient, body, _now()))
            self._event(con, rig_id, "message_sent", str(cursor.lastrowid))
            return cursor.lastrowid

    def inbox(self, rig_id: str, recipient: str, *, after: int = 0, limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 200:
            raise ValueError("Invalid inbox limit")
        with self._connection() as con:
            rows = con.execute("""SELECT id,sender,recipient,body,created_at FROM messages
                   WHERE rig_id=? AND (recipient=? OR recipient='*') AND id>?
                   ORDER BY id LIMIT ?""", (rig_id, recipient, after, limit)).fetchall()
            return [dict(row) for row in rows]

    def snapshot(self, rig_id: str) -> dict:
        with self._connection() as con:
            rig = con.execute("SELECT spec_json FROM rigs WHERE id=?", (rig_id,)).fetchone()
            if not rig:
                raise KeyError("Unknown rig")
            tasks = con.execute("SELECT * FROM tasks WHERE rig_id=? ORDER BY created_at,id", (rig_id,)).fetchall()
            return {"rig_id": rig_id, "spec": json.loads(rig["spec_json"]),
                    "tasks": [self._task(row) for row in tasks]}
