"""Human permission decisions with a durable record and hard seat-policy bounds."""
from __future__ import annotations

import json
from pathlib import Path
import time
import uuid

from .store import _json, _now
from .workspaces import safe_path


class PermissionBroker:
    def __init__(self, store):
        self.store = store
        self.identities = {}

    def request(self, handle, params, guard):
        identifier = uuid.uuid4().hex
        policy = handle.seat.policy
        subject = params.get("subject", {})
        tool = subject.get("toolCall", params.get("toolCall", {}))
        kind = tool.get("kind")
        permitted = True
        if subject.get("type") == "command" or kind == "execute":
            permitted = policy.terminal and subject.get("cwd") == str(handle.workspace.resolve())
        elif kind in {"edit", "delete", "move"}:
            permitted = policy.file_edits
            locations = tool.get("locations", [])
            if not locations:
                permitted = False
            for location in locations:
                try:
                    absolute = Path(location["path"])
                    relative = absolute.relative_to(handle.workspace.resolve()).as_posix()
                    safe_path(handle.workspace, relative)
                    permitted &= any(relative == p.rstrip("/") or relative.startswith(p.rstrip("/") + "/") for p in policy.allowed_paths)
                except (KeyError, TypeError, ValueError):
                    permitted = False
        elif kind in {"fetch", "network"}:
            permitted = policy.network
        else:
            # Unstructured/unknown permission prompts cannot establish filesystem scope.
            permitted = False
        identity = self.identities.get(handle.id, {})
        with self.store.connect(True) as con:
            con.execute("INSERT INTO permissions VALUES(?,?,?,?,?,?)", (identifier, handle.id,
                _json(params), "PENDING" if permitted else "DENIED", None, _now()))
            self.store.event(con, "permission_requested" if permitted else "permission_denied_by_policy",
                             {"permission_id": identifier, "operation": params}, **identity)
        if not permitted:
            return {"outcome": "cancelled"}
        try:
            while True:
                guard()
                with self.store.connect() as con:
                    row = con.execute("SELECT state,decision FROM permissions WHERE id=?", (identifier,)).fetchone()
                if row["state"] != "PENDING":
                    return json.loads(row["decision"]) if row["decision"] else {"outcome": "cancelled"}
                time.sleep(.1)
        finally:
            with self.store.connect(True) as con:
                con.execute("UPDATE permissions SET state='EXPIRED' WHERE id=? AND state='PENDING'", (identifier,))

    def decide(self, identifier, option_id):
        with self.store.connect(True) as con:
            row = con.execute("SELECT * FROM permissions WHERE id=?", (identifier,)).fetchone()
            if row is None or row["state"] != "PENDING":
                raise ValueError("Permission is not pending")
            options = json.loads(row["operation_json"]).get("options", [])
            option = next((o for o in options if o.get("optionId") == option_id), None)
            if option is None or option.get("kind") not in {"allow_once", "reject_once"}:
                raise ValueError("Only an advertised one-time decision is supported")
            decision = {"outcome": "selected", "optionId": option_id}
            con.execute("UPDATE permissions SET state='RESOLVED',decision=? WHERE id=?", (_json(decision), identifier))
            self.store.event(con, "permission_decided", {"permission_id": identifier, "option_id": option_id}, session_id=row["session_id"])
        return decision

    def pending(self, rig_id):
        with self.store.connect() as con:
            rows = con.execute("SELECT permissions.* FROM permissions JOIN sessions ON sessions.id=permissions.session_id WHERE sessions.rig_id=? AND permissions.state='PENDING' ORDER BY permissions.created_at", (rig_id,)).fetchall()
        return [{"id": r["id"], "session_id": r["session_id"], "operation": json.loads(r["operation_json"]), "created_at": r["created_at"]} for r in rows]
