"""Durable team scheduler and process/session continuity, independent of Kaggle admission."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
from threading import Event, RLock, Thread
import time
import uuid

from .control_store import ControlStore
from .context import ContextRouter
from .harnesses import HarnessRegistry
from .models import AgentSpec, RigSpec, TaskRequest
from .permissions import PermissionBroker
from .processes import process_identity, ProcessFailure
from .store import _json, _now
from .workspaces import Workspaces


class TeamPlatform:
    def __init__(self, queue, repository: Path, *, codex=None, registry=None, protected=()):
        self.store = ControlStore(queue)
        self.workspaces = Workspaces(repository)
        self.context = ContextRouter(repository, self.workspaces)
        self.permissions = PermissionBroker(self.store)
        self.registry = registry or HarnessRegistry(self.store, codex=codex, permission=self.permissions, repository=repository, protected=protected)
        self.active = {}
        self.lock = RLock()
        self.stopping = Event()
        self.thread = None
        self.store.recover()

    def create(self, rig_id: str, spec: RigSpec):
        from .spec import _id
        _id(rig_id, "rig ID")
        self.workspaces.revision(spec.base_ref)
        for seat in spec.seats:
            self.registry.resolve(seat.harness)
        return self.store.create(rig_id, spec)

    def enqueue(self, rig_id, seat_id, request_id, request: TaskRequest, *, depends_on=None):
        rig = self.store.rig(rig_id)
        if seat_id not in {s.id for s in rig.seats}:
            raise ValueError("Seat is not in this team")
        # Research commands use the approval-bound bridge; coding prompts cannot submit jobs.
        if request.kind == "research":
            raise ValueError("Research execution requires an approved bridge command")
        if request.input_checkpoint:
            team = self.store.snapshot(rig_id)
            known = {s['checkpoint'] for s in team['seats'] if s['checkpoint']}
            known.update(t['result']['checkpoint'] for t in team['tasks'] if t.get('result') and t['result'].get('checkpoint'))
            if request.input_checkpoint not in known:
                raise ValueError('Checkpoint does not belong to this team')
        return self.store.queue.enqueue(rig_id, seat_id, request_id, request.model_dump(), depends_on=depends_on, max_pending=256)

    def start(self, rig_id):
        if os.environ.get("AI_SCIENTIST_AGENT_ORCHESTRATION", "1") != "1":
            raise ValueError("Agent orchestration feature flag is disabled")
        self.store.enabled(rig_id, True)
        with self.lock:
            if self.thread is None or not self.thread.is_alive():
                self.stopping.clear()
                self.thread = Thread(target=self._loop, name="team-scheduler", daemon=True)
                self.thread.start()
        return self.store.snapshot(rig_id)

    def pause(self, rig_id, *, interrupt=False):
        self.store.enabled(rig_id, False)
        if interrupt:
            with self.lock:
                for identity, record in self.active.items():
                    if identity[0] == rig_id:
                        record["adapter"].interrupt(record["handle"])
        return self.store.snapshot(rig_id)

    def _loop(self):
        while not self.stopping.wait(.15):
            try:
                self.tick()
            except Exception:
                self.store.publish("scheduler_attention", {"message": "Scheduler cycle failed; inspect team task events"})

    def tick(self):
        with self.lock:
            for team in self.store.rigs():
                if not team["enabled"]:
                    continue
                rig_id = team["id"]
                rig = RigSpec.model_validate(team["spec"])
                from .resources import resource_limits
                resources = resource_limits(self.store, rig_id)
                count = sum(key[0] == rig_id for key in self.active)
                for seat in rig.seats:
                    if count >= rig.max_parallel or len(self.active) >= 32:
                        break
                    if (rig_id, seat.id) in self.active:
                        continue
                    with self.store.connect() as con:
                        status = con.execute('SELECT state FROM seats WHERE rig_id=? AND id=?', (rig_id, seat.id)).fetchone()
                    if status and status['state'] in {'UNKNOWN', 'REMOVED'}:
                        continue
                    pod = next(p for p in rig.pods if p.id == seat.pod)
                    busy_in_pod = sum(key[0] == rig_id and value["handle"].seat.pod == pod.id for key, value in self.active.items())
                    if busy_in_pod >= pod.max_parallel:
                        continue
                    if any(seat.id in r.seat_ids and sum(k[0] == rig_id and k[1] in r.seat_ids for k in self.active) >= r.max_parallel for r in resources):
                        continue
                    task = self.store.queue.claim(rig_id, seat.id, lease_seconds=30)
                    if task is None:
                        continue
                    adapter, handle, session_id = None, None, None
                    try:
                        adapter = self.registry.resolve(seat.harness)
                        path, checkpoint = self.workspaces.ensure(rig_id, seat.id, rig.base_ref)
                        self.store.seat_workspace(rig_id, seat.id, path, checkpoint)
                        handle = adapter.start(seat, path)
                        session_id = self.store.begin_session(task, seat.harness)
                        # Supervisor IDs are durable; permission requests use that same identity.
                        handle.id = session_id
                        identity = {"rig_id": rig_id, "seat_id": seat.id, "task_id": task["id"],
                                    "request_id": task["request_id"], "provider_id": seat.harness, "session_id": session_id}
                        self.permissions.identities[session_id] = identity
                        record = {"adapter": adapter, "handle": handle, "task": task, "identity": identity}
                        worker = Thread(target=self._execute, args=(rig, record), name="seat-" + seat.id, daemon=True)
                        record["thread"] = worker
                        self.active[(rig_id, seat.id)] = record
                        worker.start()
                        count += 1
                    except Exception as exc:
                        self.store.fail_task(task["id"], task["lease_token"], error=str(exc)[:1000])
                        if session_id:
                            self.store.complete_session(session_id, state='FAILED', receipt={'not_started': True, 'tree_stopped': True, 'process_exited': True})
                            self.permissions.identities.pop(session_id, None)
                            self.active.pop((rig_id, seat.id), None)

    def _execute(self, rig, record):
        task, adapter, handle, identity = [record[key] for key in ("task", "adapter", "handle", "identity")]
        token = task["lease_token"]
        heartbeat_stop = Event()
        def heartbeat():
            while not heartbeat_stop.wait(5):
                if not self.store.heartbeat(task["id"], token):
                    adapter.interrupt(handle)
                    return
        keeper = Thread(target=heartbeat, daemon=True)
        keeper.start()
        state = "FAILED"
        try:
            request = TaskRequest.model_validate(task["payload"])
            predecessor = None
            if task["depends_on"]:
                with self.store.connect() as con:
                    predecessor = con.execute("SELECT result_json FROM tasks WHERE id=?", (task["depends_on"],)).fetchone()
                    predecessor = json.loads(predecessor[0]) if predecessor and predecessor[0] else None
            if predecessor and 'files' in predecessor:
                predecessor={**predecessor,'files':[f for f in predecessor['files'] if any(
                    f['path']==p.rstrip('/') or f['path'].startswith(p.rstrip('/')+'/')
                    for p in handle.seat.policy.allowed_paths)]}
            checkpoint = request.input_checkpoint or (predecessor or {}).get("checkpoint")
            if checkpoint:
                self.workspaces.restore_checkpoint(handle.workspace, checkpoint)
            if request.resume_session:
                previous = self.store.session(request.resume_session)
                if previous["rig_id"] != task["rig_id"] or previous["seat_id"] != task["seat"] or previous["provider_id"] != handle.seat.harness:
                    raise ValueError("Resume session does not belong to this seat/provider")
                if previous["state"] not in {"DONE", "CANCELLED", "FAILED"} or not (previous.get("stop_receipt") or {}).get("tree_stopped"):
                    raise ValueError("Previous session must have a verified stop receipt")
                if not previous["provider_session"]:
                    raise ValueError("Previous session has no resumable provider token")
                if request.fork_session:
                    adapter.fork(handle, previous['provider_session'])
                else:
                    adapter.resume(handle, previous["provider_session"])
            context = self.context.pack(rig, task["seat"])
            # Structured stage requests already carry the pinned workflow inputs.
            # A team inbox can contain handoffs from a different workflow/grant.
            inbox = [] if request.structured_only else self.store.queue.inbox(task["rig_id"], task["seat"], limit=100)
            # Supply scoped source text to tool-free native agents. File reads stay in the service.
            files = []
            for entry in ([] if request.structured_only else self.workspaces.files(handle.workspace)):
                if any(entry["path"] == p.rstrip("/") or entry["path"].startswith(p.rstrip("/") + "/") for p in handle.seat.policy.allowed_paths):
                    if sum(len(f["content"]) for f in files) + entry["bytes"] > 300_000:
                        break
                    try:
                        files.append(self.workspaces.read(handle.workspace, entry["path"]))
                    except UnicodeError:
                        continue
            message = _json({"role": handle.seat.role, "instructions": handle.seat.instructions,
                             "task": request.instruction, "request_id": task["request_id"],
                             "seat_policy": handle.seat.policy.model_dump(), "context": context,
                             "files": files, "messages": inbox, "predecessor": predecessor})
            def started(proc):
                self.store.process_started(handle.id, proc.pid, process_identity(proc.pid))
            def emit(text):
                self.store.publish("output", {"text": text}, **identity)
            turn = adapter.send(handle, message, request_id=task["request_id"],
                                timeout=rig.timeout_seconds, emit=emit, started=started)
            if not turn.receipt.get("tree_stopped"):
                raise ProcessFailure("Harness outcome is unknown", turn.receipt)
            if not self.store.heartbeat(task["id"], token):
                raise ProcessFailure("Task lease expired; reconcile before applying edits", turn.receipt)
            if request.structured_only and turn.result.files:
                raise ValueError('Structured research stages cannot edit the local workspace')
            self.workspaces.apply(handle.workspace, turn.result, handle.seat.policy)
            checkpoint = self.workspaces.checkpoint(handle.workspace, task_id=task["id"])
            self.store.seat_workspace(task["rig_id"], task["seat"], handle.workspace, checkpoint)
            result = {**turn.result.model_dump(), "checkpoint": checkpoint, "session_id": handle.id}
            self.store.complete_turn(task['id'],token,handle.id,result=result,receipt=turn.receipt,
                                     provider_session=turn.provider_session,usage=turn.usage)
            state = "DONE"
            # Durable completion must survive an ancillary chat/event failure.
            try:
                handoff = (turn.result.handoff or turn.result.summary or "Task completed")[:20000]
                self.store.queue.send(task["rig_id"], task["seat"], "*", handoff)
                self.store.publish("task_done", {"checkpoint": checkpoint, "summary": turn.result.summary}, **identity)
            except Exception:
                self.store.publish('handoff_attention', {'message': 'Task completed; chat notification could not be delivered'}, **identity)
        except Exception as exc:
            if state == 'DONE':
                return
            receipt = getattr(exc, "receipt", None) or handle.stop_receipt
            # If a process was never started, there is no uncertain external execution.
            if receipt is None and not self.store.process_record(handle.id):
                receipt = {"process_exited": True, "tree_stopped": True, "not_started": True}
            uncertain = not receipt or not receipt.get("tree_stopped")
            state = "UNKNOWN" if uncertain else ("CANCELLED" if getattr(exc, "cancelled", False) or isinstance(exc,InterruptedError) else "FAILED")
            try:
                self.store.fail_task(task["id"], token, error=str(exc)[:1000], uncertain=uncertain, cancelled=state == "CANCELLED")
            except ValueError:
                state = "UNKNOWN"
            self.store.complete_session(handle.id, state=state, receipt=receipt or {})
        finally:
            heartbeat_stop.set()
            keeper.join(timeout=1)
            self.permissions.identities.pop(handle.id, None)
            with self.lock:
                self.active.pop((task["rig_id"], task["seat"]), None)

    def interrupt(self, rig_id, seat_id):
        with self.lock:
            record = self.active.get((rig_id, seat_id))
            if record is None:
                raise ValueError("Seat has no live supervised process")
            record["adapter"].interrupt(record["handle"])
            return {"session_id": record["handle"].id, "state": "STOPPING"}

    def reconcile(self, session_id, *, retry=False):
        session = self.store.session(session_id)
        if session["state"] != "UNKNOWN":
            raise ValueError("Only UNKNOWN sessions need reconciliation")
        record = self.store.process_record(session_id)
        if record is None:
            receipt = {"process_exited": True, "tree_stopped": True, "not_started": True}
        else:
            pid = record["pid"]
            current = process_identity(pid)
            if current is not None:
                if current != record["birth_identity"]:
                    # Original process ended; never kill a reused PID.
                    current = None
                else:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10)
                    else:
                        os.killpg(pid, signal.SIGKILL)
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline and process_identity(pid) == current:
                        time.sleep(.05)
                    current = process_identity(pid)
            receipt = {"pid": pid, "process_exited": current is None,
                       "tree_stopped": current is None, "verified_birth_identity": record["birth_identity"],
                       "containment": record["containment"]}
        self.store.reconcile(session_id, receipt, retry=retry)
        return self.store.session(session_id)

    def snapshot(self, rig_id):
        team = self.store.snapshot(rig_id)
        if any(s["state"] in {"BUSY", "UNKNOWN"} for s in team["seats"]):
            raise ValueError("Pause and stop/reconcile sessions before taking a restorable snapshot")
        descriptor = {"version": 1, "spec": team["spec"], "revision": team["revision"],
                      "seats": [{"id": s["id"], "checkpoint": s["checkpoint"]} for s in team["seats"]],
                      "pending_task_ids": [t["id"] for t in team["tasks"] if t["state"] == "PENDING"]}
        identifier = uuid.uuid4().hex
        with self.store.connect(True) as con:
            con.execute("INSERT INTO snapshots VALUES(?,?,?,?)", (identifier, rig_id, _json(descriptor), _now()))
            self.store.event(con, "snapshot_saved", {"snapshot_id": identifier}, rig_id=rig_id)
        return {"id": identifier, "descriptor": descriptor}

    def restore(self, rig_id, snapshot_id):
        team = self.store.snapshot(rig_id)
        if team["enabled"] or any(s["state"] in {"BUSY", "UNKNOWN"} for s in team["seats"]):
            raise ValueError("Restore requires a paused and reconciled team")
        with self.store.connect() as con:
            row = con.execute("SELECT descriptor_json FROM snapshots WHERE id=? AND rig_id=?", (snapshot_id, rig_id)).fetchone()
        if row is None:
            raise KeyError("Unknown snapshot")
        descriptor = json.loads(row[0])
        if descriptor["spec"] != team["spec"]:
            raise ValueError("Snapshot topology differs; restore into a new team using a bundle")
        for seat in descriptor["seats"]:
            if seat["checkpoint"]:
                path, _ = self.workspaces.ensure(rig_id, seat["id"], team["spec"]["base_ref"])
                self.workspaces.restore_checkpoint(path, seat["checkpoint"])
                self.store.seat_workspace(rig_id, seat["id"], path, seat["checkpoint"])
        self.store.publish("snapshot_restored", {"snapshot_id": snapshot_id}, rig_id=rig_id)
        return self.store.snapshot(rig_id)

    def adopt(self, rig_id, seat_id):
        rig = self.store.rig(rig_id)
        if seat_id not in {s.id for s in rig.seats}:
            raise ValueError("Adoption requires a configured seat")
        found = next((entry for entry in self.workspaces.discover() if entry["rig_id"] == rig_id and entry["seat_id"] == seat_id), None)
        if found is None:
            raise ValueError("No isolated worktree was discovered for this seat")
        path, checkpoint = self.workspaces.ensure(rig_id, seat_id, rig.base_ref)
        self.store.seat_workspace(rig_id, seat_id, path, checkpoint)
        self.store.publish("seat_adopted", found, rig_id=rig_id, seat_id=seat_id)
        return found

    def close(self, timeout=15):
        self.stopping.set()
        with self.lock:
            records = list(self.active.values())
            for record in records:
                record["adapter"].interrupt(record["handle"])
        deadline = time.monotonic() + timeout
        for record in records:
            record["thread"].join(timeout=max(0, deadline - time.monotonic()))
        if self.thread:
            self.thread.join(timeout=1)
        return {"stopped": not self.active, "remaining_sessions": [r["handle"].id for r in self.active.values()]}
