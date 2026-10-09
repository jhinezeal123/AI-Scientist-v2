import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import json
from threading import Event
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from ai_scientist.treesearch.journal import Journal, Node
from ai_scientist.treesearch.utils.metric import MetricValue
from ai_scientist.workbench.app import create_app
from ai_scientist.workbench.journal import journal_snapshot, restore_journal
from ai_scientist.workbench.models import validate_result
from ai_scientist.workbench.worker import RuntimeWorker


def test_journal_round_trip_without_input_mutation():
    journal = Journal()
    root = Node(plan="approved plan", code="print(1)", metric=MetricValue(2.5, maximize=False, name="EMD"))
    journal.append(root)
    child = Node(parent=root, plan="repair", code="print(2)", metric=MetricValue(1.5, maximize=False, name="EMD"))
    journal.append(child)
    snapshot = json.loads(json.dumps(journal_snapshot(journal)))
    original = deepcopy(snapshot)
    restored = restore_journal(snapshot)
    assert snapshot == original
    assert restored[1].parent is restored[0]
    assert restored[1] in restored[0].children
    assert restored[0] is not root
    assert [(n.id, n.plan, n.code, n.metric.value, n.metric.maximize) for n in restored.nodes] == [
        (n.id, n.plan, n.code, n.metric.value, n.metric.maximize) for n in journal.nodes]
    assert journal_snapshot(restored) == original


def report_result(**updates):
    data = dict(summary="ok", interpretation="transport only", limitations=[], suggested_next=[], evidence_refs=[])
    data.update(updates)
    return SimpleNamespace(text=json.dumps(data), files={})


def test_role_validation_rejects_files_and_extra_keys():
    assert validate_result("mvp0_report", report_result()).summary == "ok"
    with pytest.raises(ValidationError):
        validate_result("mvp0_report", report_result(unexpected=True))
    result = report_result()
    result.files = {"escape.py": b"code"}
    with pytest.raises(ValueError, match="empty files"):
        validate_result("mvp0_report", result)


def test_health_during_worker_and_shutdown(tmp_path):
    started, stopped = Event(), Event()
    class WaitingRuntime:
        def run(self, request, progress, cancelled):
            started.set()
            while not cancelled():
                stopped.wait(.01)
            stopped.set()
            raise RuntimeError("cancelled fixture")

    closed = []
    @asynccontextmanager
    async def connection(config):
        try:
            yield object()
        finally:
            closed.append(True)

    config = SimpleNamespace(workspace_root=tmp_path, shutdown_seconds=2)
    app = create_app(config, bindings=SimpleNamespace(runtime=WaitingRuntime()), kaggle_connection=connection)

    async def check():
        async with app.router.lifespan_context(app):
            request = SimpleNamespace(request_id="one", role="mvp0_report")
            task = asyncio.create_task(app.state.worker.run(request))
            while not started.is_set():
                await asyncio.sleep(.01)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await asyncio.wait_for(client.get("/health"), .5)
                assert response.json()["runtime_job"] == "running"
            with pytest.raises(RuntimeError, match="busy"):
                await app.state.worker.run(request)
        with pytest.raises(RuntimeError):
            await task
        assert stopped.is_set() and closed
        assert app.state.worker.state["status"] == "interrupted"

    asyncio.run(check())


def test_restart_marks_inflight_interrupted_without_replay(tmp_path):
    state = tmp_path / "runtime-state.json"
    state.write_text(json.dumps({"status": "running", "request_id": "old"}))
    worker = RuntimeWorker(object(), state)
    assert worker.state == {"status": "interrupted", "request_id": "old"}
    assert worker.future is None
    asyncio.run(worker.close(1))


def test_unconfirmed_runtime_stop_is_unknown(tmp_path):
    class Uncertain(RuntimeError):
        pass
    class Runtime:
        def run(self, request, progress, cancelled):
            raise Uncertain("child not confirmed stopped")
    worker = RuntimeWorker(Runtime(), tmp_path / "state.json", uncertain_error=Uncertain)
    async def check():
        with pytest.raises(Uncertain):
            await worker.run(SimpleNamespace(request_id="one", role="mvp0_report"))
        assert worker.state["status"] == "unknown"
        with pytest.raises(RuntimeError, match="uncertain"):
            await worker.run(SimpleNamespace(request_id="two", role="mvp0_report"))
        await worker.close(1)
    asyncio.run(check())
