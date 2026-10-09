"""One blocking runtime job off the event loop, with cancellation on shutdown."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import inspect
import json
from pathlib import Path
from threading import Event
from pydantic import ValidationError

from .models import validate_result


class RuntimeWorker:
    def __init__(self, runtime, state_path: Path, *, uncertain_error=None):
        self.runtime = runtime
        self.uncertain_error = uncertain_error
        self.state_path = state_path
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="workbench-codex")
        self.cancelled = Event()
        self.future = None
        self.closed = False
        self.state = {"status": "idle"}
        if state_path.exists():
            self.state = json.loads(state_path.read_text(encoding="utf-8"))
            if self.state.get("status") == "running":
                self._save({**self.state, "status": "interrupted"})

    def _save(self, state):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state), encoding="utf-8")
        temporary.replace(self.state_path)
        self.state = state

    async def run(self, request, *, on_result=None):
        if self.future is not None and self.future.done():
            self.future = None
        if self.closed or self.future is not None:
            raise RuntimeError("Runtime worker is closed or busy")
        if self.state.get("status") == "unknown":
            raise RuntimeError("Previous runtime outcome is uncertain; reconcile before another job")
        # Validate the role before starting any process.
        from .models import ROLE_PAYLOADS
        if request.role not in ROLE_PAYLOADS:
            raise ValueError("Unsupported workbench role")
        self.cancelled.clear()
        self._save({"status": "running", "request_id": request.request_id, "role": request.role})
        self.future = self.executor.submit(self.runtime.run, request, lambda event: None,
                                           self.cancelled.is_set)
        result = None
        try:
            result = await asyncio.shield(asyncio.wrap_future(self.future))
            payload = validate_result(request.role, result)
            if on_result is not None:
                persisted = on_result(payload)
                if inspect.isawaitable(persisted):
                    await persisted
            self._save({**self.state, "status": self.state["status"] if self.closed else "completed"})
            return result, payload
        except BaseException as exc:
            self.cancelled.set()
            unknown = isinstance(exc, asyncio.CancelledError) or (
                self.uncertain_error is not None and isinstance(exc, self.uncertain_error))
            status = "unknown" if unknown else "interrupted" if self.closed else "failed"
            failure = {**self.state, "status": status}
            # Persist only adapter-authored messages, never model output or stderr.
            known_errors = {
                'Codex CLI output exceeded its configured size limit',
                'Codex CLI event stream was not UTF-8',
                'Codex CLI emitted an invalid JSONL event',
                'Codex CLI emitted an invalid event',
                'Codex CLI turn failed',
                'Codex CLI reported an error',
                'Codex CLI stream has no completed agent message',
                'Codex CLI turn did not complete cleanly',
                'Codex CLI final response was not valid JSON',
                'Codex CLI final response does not match the agent result schema',
                'Codex CLI final response is missing text',
                'Workbench results must have an empty files envelope',
                'Role result text must contain one JSON object',
            }
            if isinstance(exc, ValueError) and str(exc) in known_errors:
                failure['error'] = str(exc)
            if isinstance(exc, ValidationError):
                allowed = ROLE_PAYLOADS[request.role].model_fields
                failure['validation_errors'] = [
                    {'field': issue['loc'][0] if issue['loc'] and issue['loc'][0] in allowed else 'payload',
                     'type': issue['type']}
                    for issue in exc.errors(include_input=False, include_context=False, include_url=False)[:20]
                ]
                session_id = getattr(result, 'session_id', None)
                if isinstance(session_id, str) and len(session_id) <= 256:
                    failure['session_id'] = session_id
            self._save(failure)
            raise
        finally:
            # Retain a running future after caller cancellation: no second admission.
            if self.future.done():
                self.future = None

    async def close(self, timeout):
        self.closed = True
        self.cancelled.set()
        if self.future is not None:
            self._save({**self.state, "status": "interrupted"})
            try:
                await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(self.future)), timeout)
            except (Exception, asyncio.CancelledError) as exc:
                if isinstance(exc, (TimeoutError, asyncio.CancelledError)) or (
                    self.uncertain_error is not None and isinstance(exc, self.uncertain_error)):
                    self._save({**self.state, "status": "unknown"})
        self.executor.shutdown(wait=False, cancel_futures=True)
