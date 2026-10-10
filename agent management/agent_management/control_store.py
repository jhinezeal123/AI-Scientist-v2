"""Team/session persistence; research runs remain in their existing project DB."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from .migrations import migrate
from .models import RigSpec, HarnessSpec
from .store import AgentStore, _json, _now


class ControlStore:
    def __init__(self, queue: AgentStore):
        self.queue = queue
        self.path = queue.path
        with queue._connection():
            pass
        migrate(self.path)

    @contextmanager
    def connect(self, write=False):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA busy_timeout=15000")
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

    @staticmethod
    def event(con, kind: str, data: dict | None = None, **identity):
        keys = ("rig_id", "seat_id", "task_id", "request_id", "provider_id", "session_id")
        cursor = con.execute("""INSERT INTO journal(rig_id,seat_id,task_id,request_id,
            provider_id,session_id,kind,data_json,timestamp) VALUES(?,?,?,?,?,?,?,?,?)""",
            (*[identity.get(k) for k in keys], kind, _json(data or {}), _now()))
        return cursor.lastrowid

    def publish(self, kind: str, data: dict | None = None, **identity):
        with self.connect(True) as con:
            return self.event(con, kind, data, **identity)

    def events(self, *, rig_id: str | None = None, after=0, limit=200):
        if after < 0 or not 1 <= limit <= 500:
            raise ValueError("Invalid journal cursor")
        with self.connect() as con:
            rows = con.execute("""SELECT * FROM journal WHERE id>? AND (? IS NULL OR rig_id=?)
                ORDER BY id LIMIT ?""", (after, rig_id, rig_id, limit)).fetchall()
        return [{**{k: row[k] for k in row.keys() if k != "data_json"},
                 "data": json.loads(row["data_json"])} for row in rows]

    def put_harness(self, spec: HarnessSpec):
        with self.connect(True) as con:
            con.execute("INSERT OR REPLACE INTO harnesses VALUES(?,?)", (spec.id, _json(spec.model_dump())))
            self.event(con, "harness_configured", {"id": spec.id, "kind": spec.kind})

    def harnesses(self):
        with self.connect() as con:
            return [HarnessSpec.model_validate_json(row[0])
                    for row in con.execute("SELECT spec_json FROM harnesses ORDER BY id")]

    def create(self, rig_id: str, spec: RigSpec):
        self.queue.create_rig(rig_id, spec.model_dump())
        with self.connect(True) as con:
            con.execute("INSERT OR IGNORE INTO rig_runtime(rig_id) VALUES(?)", (rig_id,))
            for seat in spec.seats:
                con.execute("INSERT OR IGNORE INTO seats(rig_id,id) VALUES(?,?)", (rig_id, seat.id))
            self.event(con, "team_created", {"name": spec.name}, rig_id=rig_id)
        return self.snapshot(rig_id)

    def rigs(self):
        with self.connect() as con:
            return [{"id": row["id"], "spec": json.loads(row["spec_json"]),
                     "enabled": bool(row["enabled"]), "revision": row["revision"]}
                    for row in con.execute("SELECT rigs.*,enabled,revision FROM rigs JOIN rig_runtime ON rigs.id=rig_id ORDER BY created_at")]

    def rig(self, rig_id: str) -> RigSpec:
        with self.connect() as con:
            row = con.execute("SELECT spec_json FROM rigs WHERE id=?", (rig_id,)).fetchone()
            if row is None:
                raise KeyError("Unknown team")
            return RigSpec.model_validate_json(row[0])

    def snapshot(self, rig_id):
        result = self.queue.snapshot(rig_id)
        with self.connect() as con:
            runtime = con.execute("SELECT enabled,revision FROM rig_runtime WHERE rig_id=?", (rig_id,)).fetchone()
            if runtime is None:
                raise ValueError("This is a legacy metadata rig, not an executable team")
            result.update(dict(runtime))
            result["seats"] = [dict(row) for row in con.execute("SELECT * FROM seats WHERE rig_id=? ORDER BY id", (rig_id,))]
            tasks = con.execute("SELECT * FROM tasks WHERE rig_id=? ORDER BY created_at,id", (rig_id,))
            result["tasks"] = [{**self.queue._task(row), "payload": json.loads(row["payload_json"]),
                               "result": json.loads(row["result_json"]) if row["result_json"] else None}
                              for row in tasks]
            result["sessions"] = [self.session_row(row) for row in con.execute("SELECT * FROM sessions WHERE rig_id=? ORDER BY created_at", (rig_id,))]
        return result

    @staticmethod
    def session_row(row):
        result = dict(row)
        for field in ("stop_receipt_json", "usage_json"):
            result[field.removesuffix("_json")] = json.loads(result.pop(field)) if row[field] else None
        return result

    def enabled(self, rig_id, value: bool):
        with self.connect(True) as con:
            if not con.execute("SELECT 1 FROM rig_runtime WHERE rig_id=?", (rig_id,)).fetchone():
                raise KeyError("Unknown team")
            con.execute("UPDATE rig_runtime SET enabled=? WHERE rig_id=?", (int(value), rig_id))
            self.event(con, "team_started" if value else "team_paused", rig_id=rig_id)

    def update_spec(self, rig_id, spec: RigSpec, revision: int):
        with self.connect(True) as con:
            current = con.execute("SELECT revision FROM rig_runtime WHERE rig_id=?", (rig_id,)).fetchone()
            if current is None:
                raise KeyError("Unknown team")
            if current[0] != revision:
                raise ValueError("Team revision changed; refresh before editing")
            active = con.execute("SELECT 1 FROM tasks WHERE rig_id=? AND state IN ('LEASED','UNKNOWN','PENDING')", (rig_id,)).fetchone()
            if active:
                raise ValueError("Pause and resolve queued/active tasks before changing topology")
            old = self.rig(rig_id)
            if (old.project_id, old.base_ref) != (spec.project_id, spec.base_ref):
                raise ValueError("Project and base ref are immutable; create a new team")
            con.execute("UPDATE rigs SET spec_json=? WHERE id=?", (_json(spec.model_dump()), rig_id))
            con.execute("UPDATE rig_runtime SET revision=revision+1 WHERE rig_id=?", (rig_id,))
            names = {s.id for s in spec.seats}
            for seat in spec.seats:
                con.execute("INSERT OR IGNORE INTO seats(rig_id,id) VALUES(?,?)", (rig_id, seat.id))
            for seat in old.seats:
                if seat.id not in names:
                    con.execute("UPDATE seats SET state='REMOVED' WHERE rig_id=? AND id=?", (rig_id, seat.id))
            self.event(con, "topology_changed", {"revision": revision + 1}, rig_id=rig_id)

    def seat_workspace(self, rig_id, seat_id, path, checkpoint):
        with self.connect(True) as con:
            con.execute("UPDATE seats SET worktree=?,checkpoint=? WHERE rig_id=? AND id=?", (str(path), checkpoint, rig_id, seat_id))

    def begin_session(self, task, provider_id):
        session_id = uuid.uuid4().hex
        with self.connect(True) as con:
            now = _now()
            con.execute("""INSERT INTO sessions(id,rig_id,seat_id,task_id,request_id,provider_id,state,created_at,updated_at)
                VALUES(?,?,?,?,?,?,'STARTING',?,?)""", (session_id, task["rig_id"], task["seat"], task["id"], task["request_id"], provider_id, now, now))
            con.execute("UPDATE seats SET state='BUSY',session_id=? WHERE rig_id=? AND id=?", (session_id, task["rig_id"], task["seat"]))
            self.event(con, "session_starting", rig_id=task["rig_id"], seat_id=task["seat"], task_id=task["id"], request_id=task["request_id"], provider_id=provider_id, session_id=session_id)
        return session_id

    def process_started(self, session_id, process_id, birth_identity=None):
        with self.connect(True) as con:
            con.execute("UPDATE sessions SET state='RUNNING',process_id=?,updated_at=? WHERE id=?", (process_id, _now(), session_id))
            row = con.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            self.event(con, "process_started", {"pid": process_id, "birth_identity": birth_identity,
                       "containment": "job" if __import__("os").name == "nt" else "process_group"},
                       rig_id=row["rig_id"], seat_id=row["seat_id"], task_id=row["task_id"],
                       request_id=row["request_id"], provider_id=row["provider_id"], session_id=session_id)

    def process_record(self, session_id):
        with self.connect() as con:
            row = con.execute("SELECT data_json FROM journal WHERE session_id=? AND kind='process_started' ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def complete_session(self, session_id, *, state, receipt, provider_session=None, usage=None):
        with self.connect(True) as con:
            row = con.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None:
                raise KeyError("Unknown session")
            con.execute("UPDATE sessions SET state=?,stop_receipt_json=?,provider_session=?,usage_json=?,updated_at=? WHERE id=?", (state, _json(receipt), provider_session, _json(usage or {}), _now(), session_id))
            con.execute("UPDATE seats SET state=? WHERE rig_id=? AND id=?", ("UNKNOWN" if state == "UNKNOWN" else "IDLE", row["rig_id"], row["seat_id"]))
            self.event(con, "session_finished", {"state": state, "receipt": receipt, "usage": usage or {}},
                       rig_id=row["rig_id"], seat_id=row["seat_id"], task_id=row["task_id"],
                       request_id=row["request_id"], provider_id=row["provider_id"], session_id=session_id)

    def session(self, session_id):
        with self.connect() as con:
            row = con.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None:
                raise KeyError("Unknown session")
            return self.session_row(row)

    def heartbeat(self, task_id, token, seconds=30):
        until = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        with self.connect(True) as con:
            cursor = con.execute("UPDATE tasks SET lease_until=? WHERE id=? AND state='LEASED' AND lease_token=? AND lease_until>?", (until, task_id, token, _now()))
            return cursor.rowcount == 1

    def fail_task(self, task_id, token, *, error, uncertain=False, cancelled=False):
        with self.connect(True) as con:
            row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None or row["state"] != "LEASED" or row["lease_token"] != token:
                raise ValueError("Task is fenced")
            state = "UNKNOWN" if uncertain or row["lease_until"] <= _now() else ("CANCELLED" if cancelled else "FAILED")
            con.execute("UPDATE tasks SET state=?,lease_token=NULL,result_json=? WHERE id=?", (state, _json({"error": error}), task_id))
            self.event(con, "task_" + state.lower(), {"error": error}, rig_id=row["rig_id"], seat_id=row["seat"], task_id=task_id, request_id=row["request_id"])

    def recover(self):
        # Previous supervisor may have died while its child was still alive. Never replay.
        with self.connect(True) as con:
            rows = con.execute("SELECT * FROM sessions WHERE state IN ('STARTING','RUNNING','STOPPING')").fetchall()
            for row in rows:
                con.execute("UPDATE sessions SET state='UNKNOWN',updated_at=? WHERE id=?", (_now(), row["id"]))
                con.execute("UPDATE tasks SET state='UNKNOWN',lease_token=NULL WHERE id=? AND state='LEASED'", (row["task_id"],))
                con.execute("UPDATE seats SET state='UNKNOWN' WHERE rig_id=? AND id=?", (row["rig_id"], row["seat_id"]))
                self.event(con, "session_recovery_required", rig_id=row["rig_id"], seat_id=row["seat_id"], task_id=row["task_id"], session_id=row["id"])

    def reconcile(self, session_id, receipt, *, retry=False):
        if not receipt.get("process_exited") or not receipt.get("tree_stopped"):
            raise ValueError("A verified stop receipt is required before reconciliation")
        with self.connect(True) as con:
            row = con.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None or row["state"] != "UNKNOWN":
                raise ValueError("Session is not UNKNOWN")
            con.execute("UPDATE sessions SET state='CANCELLED',stop_receipt_json=?,updated_at=? WHERE id=?", (_json(receipt), _now(), session_id))
            con.execute("UPDATE tasks SET state=?,lease_token=NULL,lease_until=NULL WHERE id=? AND state='UNKNOWN'", ("PENDING" if retry else "CANCELLED", row["task_id"]))
            con.execute("UPDATE seats SET state='IDLE' WHERE rig_id=? AND id=?", (row["rig_id"], row["seat_id"]))
            self.event(con, "session_reconciled", {"retry": retry, "receipt": receipt}, rig_id=row["rig_id"], seat_id=row["seat_id"], task_id=row["task_id"], session_id=session_id)

    def cancel_pending(self, rig_id, task_id):
        with self.connect(True) as con:
            cursor = con.execute("UPDATE tasks SET state='CANCELLED' WHERE id=? AND rig_id=? AND state='PENDING'", (task_id, rig_id))
            if not cursor.rowcount:
                raise ValueError("Only a pending task can be cancelled without a stop receipt")
            self.event(con, "task_cancelled", rig_id=rig_id, task_id=task_id)

    def chatroom(self, rig_id, after=0):
        self.rig(rig_id)
        with self.connect() as con:
            return [dict(row) for row in con.execute("SELECT * FROM messages WHERE rig_id=? AND id>? ORDER BY id LIMIT 200", (rig_id, after))]
