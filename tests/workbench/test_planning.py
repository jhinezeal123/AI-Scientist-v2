import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace
from contextlib import asynccontextmanager
import time
from threading import Event

import pytest

from ai_scientist.workbench.models import PlanPayload, ReadyProposal
from ai_scientist.workbench.service import PlanningService
from ai_scientist.workbench.store import ProjectStore, StoreConflict
from ai_scientist.workbench.worker import RuntimeWorker
from ai_scientist.workbench.app import create_app
from fastapi.testclient import TestClient


def ready(source_id):
    return {"needs_clarification": False, "questions": [], "paraphrase": "small real-data baseline",
        "objective": "validate a small baseline", "data_refs": [source_id],
        "split": {"method": "20 train / 4 validation groups", "group_key": "sample_id", "subset": "24 real soil samples, images capped", "seed": 42},
        "metric": {"name": "EMD", "direction": "minimize", "definition": "sample mean of log10 weighted absolute cumulative error"},
        "implementation_steps": ["verify mount before submit", "train a small model"],
        "budget": {"coder_calls": 2, "training_attempts": 1, "training_seconds": 600, "output_bytes": 10000000},
        "expected_outputs": ["result.json", "metrics.json"]}


def request_type(request_id, role, prompt, workdir, **kwargs):
    return SimpleNamespace(request_id=request_id, role=role, prompt=prompt, workdir=workdir, **kwargs)


class FakeRuntime:
    def __init__(self):
        self.calls = []
        self.clarify = True
        self.invalid = False

    def run(self, request, progress, cancelled):
        self.calls.append(request)
        assert request.role == "mvp0_plan"
        context = json.loads(request.prompt.split("UNTRUSTED PROJECT CONTEXT:\n")[1])
        if self.invalid:
            body = {"needs_clarification": True, "questions": ["which model?"], "paraphrase": "idea", "source": "print('forbidden')"}
        elif self.clarify:
            body = {"needs_clarification": True, "questions": ["which baseline model?"], "paraphrase": "small baseline"}
        else:
            body = ready(context["resources"][0]["id"])
        return SimpleNamespace(text=json.dumps(body), files={})


def setup(tmp_path):
    store = ProjectStore(tmp_path / ".workbench/projects")
    project = store.create_project("test")["id"]
    source = store.save_resource(project, {"kind": "dataset", "title": "soil", "url": None, "content": "real soil source"})
    idea = store.save_idea(project, "small baseline")
    fake = FakeRuntime()
    worker = RuntimeWorker(fake, tmp_path / "worker.json")
    service = PlanningService(store, SimpleNamespace(request_type=request_type), worker, tmp_path)
    return store, project, source, idea, fake, worker, service


def test_clarification_gate_stale_approval_and_double_click(tmp_path):
    store, project, source, idea, fake, worker, service = setup(tmp_path)
    async def check():
        await service.start(project, idea["id"], [source["id"]])
        await service.task
        clarification = store.proposals(project)[0]
        assert clarification["state"] == "NEEDS_CLARIFICATION"
        assert len(fake.calls) == 1
        with pytest.raises(StoreConflict):
            await service.approve(project, clarification["id"], 1, clarification["context_sha256"])
        with pytest.raises(KeyError):
            await service.implementation_context(project, "unapproved")
        await service.answer(project, idea["id"], clarification["id"], 1, "small CNN with no pretrained weights")
        fake.clarify = False
        await service.start(project, idea["id"], [source["id"]])
        await service.task
        proposal = store.proposals(project)[0]
        assert proposal["version"] == 2 and proposal["state"] == "AWAITING_APPROVAL"
        assert len(fake.calls) == 2
        assert not list(tmp_path.rglob("workload.py")) and not list(tmp_path.rglob("*.ipynb"))
        assert store.history(project)["runs"] == []
        source2 = store.save_resource(project, {"kind": "dataset", "title": "soil", "url": None, "content": "changed source"}, source["id"], 1)
        with pytest.raises(StoreConflict):
            await service.approve(project, proposal["id"], 2, proposal["context_sha256"])
        await service.start(project, idea["id"], [source["id"]])
        await service.task
        current = store.proposals(project)[0]
        with pytest.raises(StoreConflict):
            await service.approve(project, current["id"], current["version"], "0"*64)
        first, second = await asyncio.gather(
            service.approve(project, current["id"], current["version"], current["context_sha256"]),
            service.approve(project, current["id"], current["version"], current["context_sha256"]))
        assert first["id"] == second["id"]
        assert len(store.history(project)["runs"]) == 1
        assert len(fake.calls) == 3 and all(call.role == "mvp0_plan" for call in fake.calls)
        frozen = await service.implementation_context(project, first["id"])
        assert frozen["snapshot"]["resources"][0]["version"] == source2["version"]
        store.save_resource(project, {"kind": "dataset", "title": "soil", "url": None, "content": "later source"}, source["id"], 2)
        assert (await service.implementation_context(project, first["id"])) == frozen
        await service.close()
        await worker.close(1)
    asyncio.run(check())


def test_invalid_code_payload_never_becomes_a_proposal(tmp_path):
    store, project, source, idea, fake, worker, service = setup(tmp_path)
    fake.invalid = True
    async def check():
        await service.start(project, idea["id"], [source["id"]])
        await service.task
        assert store.idea(project, idea["id"])["state"] == "FAILED"
        assert store.proposals(project) == []
        assert store.history(project)["runs"] == []
        assert len(fake.calls) == 1  # parse failure does not loop or silently retry
        assert not list(tmp_path.rglob("workload.py"))
        await service.close()
        await worker.close(1)
    asyncio.run(check())


def test_idea_edit_and_restart_do_not_replay(tmp_path):
    store, project, source, idea, fake, worker, service = setup(tmp_path)
    fake.clarify = False
    async def check():
        await service.start(project, idea["id"], [source["id"]])
        await service.task
        proposal = store.proposals(project)[0]
        store.update_idea(project, idea["id"], "changed objective", idea["text"])
        with pytest.raises(StoreConflict):
            await service.approve(project, proposal["id"], 1, proposal["context_sha256"])
        store.reserve_plan(project, idea["id"])
        restarted = ProjectStore(tmp_path / ".workbench/projects")
        restarted.recover_planning()
        assert restarted.idea(project, idea["id"])["state"] == "FAILED"
        assert len(fake.calls) == 1
        await service.close()
        await worker.close(1)
    asyncio.run(check())


def test_budget_contract_and_incomplete_clarification():
    assert PlanPayload.model_validate({"needs_clarification": True, "questions": ["model?"], "paraphrase": "idea"}).objective is None
    legacy = ready("source")
    legacy["budget"]["training_attempts"] = 2
    assert ReadyProposal.model_validate(legacy).budget.training_attempts == 2
    invalid = ready("source")
    invalid["budget"]["training_seconds"] = 601
    with pytest.raises(ValueError):
        ReadyProposal.model_validate(invalid)


def test_atomic_approval_across_threads_and_project_isolation(tmp_path):
    store, project, source, idea, fake, worker, service = setup(tmp_path)
    context = store.context_snapshot(project, idea["id"], [source["id"]])
    proposal_id = store.save_proposal(project, idea["id"], ready(source["id"]), context)
    def approve():
        return store.approve_proposal(project, proposal_id, 1, context["context_sha256"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = list(pool.map(lambda _: approve(), range(2)))
    assert runs[0]["id"] == runs[1]["id"]
    other = store.create_project("other")["id"]
    with pytest.raises(KeyError):
        store.approve_proposal(other, proposal_id, 1, context["context_sha256"])
    assert store.history(other)["runs"] == []
    asyncio.run(worker.close(1))


def test_http_planner_approval_gate_never_calls_mcp_or_coder(tmp_path):
    fake = FakeRuntime()
    fake.clarify = False
    mcp_calls = []
    class MCP:
        async def call_tool(self, *args, **kwargs):
            mcp_calls.append(args)
            raise AssertionError("No MCP workload call is authorized in T04")
    @asynccontextmanager
    async def connection(config):
        yield MCP()
    config = SimpleNamespace(workspace_root=tmp_path, shutdown_seconds=2)
    bindings = SimpleNamespace(runtime=fake, request_type=request_type)
    with TestClient(create_app(config, bindings=bindings, kaggle_connection=connection)) as client:
        project = client.post('/api/projects',json={'name':'test'}).json()['id']
        base = '/api/projects/'+project
        source = client.post(base+'/resources',json={'kind':'text','title':'data','content':'real data'}).json()
        idea = client.post(base+'/ideas',json={'text':'small baseline'}).json()
        body = {'idea_id':idea['id'],'resource_ids':[source['id']]}
        assert client.post(base+'/plan',json={**body,'role':'mvp0_code'}).status_code == 422
        assert fake.calls == []
        assert client.post(base+'/plan',json=body).status_code == 202
        deadline = time.monotonic()+5
        while True:
            proposals = client.get(base+'/proposals').json()
            if proposals:break
            assert time.monotonic()<deadline
            time.sleep(.01)
        proposal = proposals[0]
        assert client.get('/health').status_code == 200
        stale = {'version':2,'context_sha256':proposal['context_sha256']}
        assert client.post(base+f"/proposals/{proposal['id']}/approve",json=stale).status_code == 409
        approval = {'version':1,'context_sha256':proposal['context_sha256']}
        first = client.post(base+f"/proposals/{proposal['id']}/approve",json=approval)
        second = client.post(base+f"/proposals/{proposal['id']}/approve",json=approval)
        assert first.status_code == second.status_code == 200
        assert first.json()['id'] == second.json()['id']
        assert len(fake.calls) == 1 and mcp_calls == []
        assert not list(tmp_path.rglob('workload.py')) and not list(tmp_path.rglob('*.ipynb'))


def test_source_changed_while_planner_is_busy_is_not_saved(tmp_path):
    store, project, source, idea, fake, worker, service = setup(tmp_path)
    started, release = Event(), Event()
    original = fake.run
    def waiting(request, progress, cancelled):
        started.set()
        assert release.wait(3)
        return original(request, progress, cancelled)
    fake.run = waiting
    async def check():
        await service.start(project, idea['id'], [source['id']])
        while not started.is_set():await asyncio.sleep(.01)
        with pytest.raises(StoreConflict):
            await service.start(project, idea['id'], [source['id']])
        store.save_resource(project, {'kind':'text','title':'changed','url':None,'content':'new text'}, source['id'],1)
        release.set()
        await service.task
        assert store.proposals(project) == []
        assert store.idea(project,idea['id'])['state'] == 'FAILED'
        assert len(fake.calls) == 1
        await service.close()
        await worker.close(1)
    asyncio.run(check())
