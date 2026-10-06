"""One blocking runtime job off the event loop, with cancellation on shutdown."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import inspect
import json
from pathlib import Path
from threading import Event

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
            self._save({**self.state, "status": status})
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
