"""Project grants, copied presets and human gates without paid providers/Kaggle."""
import asyncio
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from ai_scientist.workbench.agents.contracts import RuntimeRequest
from ai_scientist.workbench.n8n_api import create_n8n_router
from ai_scientist.workbench.n8n_workflows import N8nResearchWorkflows, PHASES
from ai_scientist.workbench.runtime import _agent_gateway_class
from ai_scientist.workbench.service import PlanningService
from ai_scientist.workbench.store import ProjectStore, StoreConflict
from ai_scientist.workbench.worker import RuntimeWorker
from ai_scientist.workbench.workflow_models import WorkflowSpec, STAGES
from ai_scientist.workbench.stage_runtime import StageRuntime
from tests.workbench.test_stage_workflows import FixtureWorking, run_async
from tests.workbench.test_agent_team_execution import repository

Gateway = _agent_gateway_class()
P = Gateway.__module__.rsplit('.', 1)[0]


def test_n8n_human_execution_and_review_use_the_selected_actor(repository,monkeypatch):
    owner,project,_,spec,_=setup(repository)
    spec=spec.model_copy(deep=True)
    spec.stages['execution'].actor='human'
    identity=uuid.uuid4().hex
    owner.create(project,identity,spec)
    owner.store.change(project,identity,lambda s:s.update(status='RUNNING'))
    runtime=StageRuntime(owner,project,identity)
    workdir=repository/'human-execution';workdir.mkdir()
    (workdir/'terminal-access.json').write_text(json.dumps({'url':'http://127.0.0.1:8001/terminal','token':'fixture-only'}))
    result={'succeeded':True,'summary':'Human finished','limitations':[],'output_files':[]}
    human_calls=[]
    def human(stage,prompt,*args):
        human_calls.append(stage)
        return {'action':'finish','result':result}
    monkeypatch.setattr(runtime,'human',human)
    monkeypatch.setattr(owner.agent_turns,'remote',lambda *args:pytest.fail('Human execution must not call a provider'))
    reply=runtime.run(RuntimeRequest('run','mvp0_working','Execute',workdir),lambda _:None,lambda:False)
    assert json.loads(reply.text)==result and human_calls==['execution']

    runtime.spec.stages['execution'].actor='agent'
    runtime.spec.stages['execution'].ask=True
    monkeypatch.setattr(owner.agent_turns,'remote',lambda *args:result)
    monkeypatch.setattr(runtime,'human',lambda *args:{'approve':False})
    with pytest.raises(ValueError,match='Human rejected'):
        runtime.run(RuntimeRequest('run','mvp0_working','Execute',workdir),lambda _:None,lambda:False)


class FixtureClient:
    token, base_url = 'fixture-bridge', 'http://127.0.0.1:5678'
    def __init__(self):
        self.requests = []
    def status(self):
        return {'ready': True, 'workflow_url': self.base_url+'/workflow/workbenchResearch'}
    def dispatch(self, name, body):
        self.requests.append((name, body))


class FixtureAdapter:
    def __init__(self):
        self.calls = []
    def probe(self):
        return {'ready': True}
    def start(self, agent, workspace):
        return SimpleNamespace(seat=agent, stop_receipt=None)
    def send(self, handle, message, **kwargs):
        self.calls.append(handle.seat.model)
        value = json.loads(message)
        assert value['stage'] == 'proposal'
        result = {'needs_clarification': False, 'questions': [], 'paraphrase': 'Check checksum',
                  'objective': 'Check checksum', 'implementation_steps': ['Execute checksum cases'],
                  'expected_outputs': ['A checksum result JSON'], 'data_refs': [],
                  'budget': {'execution_seconds': 60, 'output_bytes': 1000}, 'research': None}
        handle.stop_receipt = {'tree_stopped': True, 'process_exited': True}
        return SimpleNamespace(result=SimpleNamespace(summary=json.dumps(result), files=[]), receipt=handle.stop_receipt)
    def close(self, handle):
        pass
    def interrupt(self, handle):
        pass


def setup(repository, *, max_runs=1):
    projects = ProjectStore(repository/'.workbench/projects', repository)
    project = projects.create_project('n8n fixture')['id']
    gateway = Gateway(SimpleNamespace(executable='', model='copied-model'), repository)
    gateway.projects = projects
    gateway.harness_catalog
    importlib.import_module(P+'.presets').Presets(gateway.control_store, default_model='copied-model')
    adapter = FixtureAdapter()
    gateway._harness_catalog = SimpleNamespace(resolve=lambda _: adapter, store=gateway.control_store, _provider_setup=None)
    worker = RuntimeWorker(SimpleNamespace(run=lambda *args: None), repository/'.workbench/planner.json')
    planner = PlanningService(projects, SimpleNamespace(request_type=RuntimeRequest), worker, repository)
    owner = N8nResearchWorkflows(planner, FixtureWorking(projects), gateway, client=FixtureClient())
    spec = WorkflowSpec(goal='Check checksum', mode='etc', desired_output='A checksum result JSON',
        account='fixture', execution_seconds=60, ttl_seconds=180, output_bytes=1000, max_runs=max_runs, search={'enabled': False},
        stages={s: {'actor': 'human' if s in {'ideation', 'approval'} else 'agent', 'preset_id': 'default'} for s in STAGES})
    identity = uuid.uuid4().hex
    owner.create(project, identity, spec)
    return owner, project, identity, spec, adapter


async def wait_for(predicate):
    for _ in range(200):
        value = predicate()
        if value:
            return value
        await asyncio.sleep(.02)
    raise AssertionError('Fixture operation did not finish')


@run_async
async def test_n8n_steps_require_each_human_gate_and_admit_once(repository):
    owner, project, identity, spec, adapter = setup(repository)
    # Unit transport runs the same provider executor; live integration tests use n8n.
    owner.agent_turns.invoke = owner.executor.invoke
    await owner.start(project, identity)
    generation = owner.store.get(project, identity)['state']['generation']
    assert owner.client.requests[0][0] == 'research'
    with pytest.raises(StoreConflict):
        await owner.step(project, identity, generation, 0, 'execution')
    for phase in PHASES:
        result = await owner.step(project, identity, generation, 0, phase, 'fixture-execution')
        assert result['pending']
        if phase in {'ideation', 'approval', 'run_approval'}:
            pending = await wait_for(lambda: next((i for i in owner.store.inputs(project, identity) if i['state'] == 'PENDING'), None))
            assert owner.working.admissions == 0
            owner.store.answer(project, identity, pending['id'], {'title': 'Checksum', 'text': 'Verify checksum'} if phase == 'ideation'
                               else {'approve': True, 'reason': 'Approved exact candidate'})
        await wait_for(lambda: owner.tasks[(identity, '0:'+phase)].done())
        first = await owner.step(project, identity, generation, 0, phase)
        assert not first['pending'] and not first['failed'], first
        assert await owner.step(project, identity, generation, 0, phase) == first
    assert owner.working.admissions == 1
    assert adapter.calls == ['copied-model']
    assert owner.view(project, identity)['state']['status'] == 'DONE'
    assert owner.gateway._platform is None
    assert (owner.projects.directory(project)/'automation'/identity/'grant.json').is_file()
    assert (await owner.pause(project, identity))['state']['status'] == 'DONE'
    assert (await owner.reconcile(project, identity))['state']['status'] == 'DONE'
    await owner.close()


def test_saved_workflow_copies_presets_and_rejects_cross_project(repository):
    owner, project, identity, _, _ = setup(repository)
    presets = importlib.import_module(P+'.presets').Presets(owner.gateway.control_store)
    model = importlib.import_module(P+'.presets').AgentPreset
    presets.put(model(id='default', name='Changed', harness='codex', model='new-model'))
    row = owner.view(project, identity)
    assert row['spec']['stages']['proposal']['model'] == 'copied-model'
    other = owner.projects.create_project('Other')['id']
    with pytest.raises(KeyError):
        owner.view(other, identity)
    assert owner.gateway._platform is None


def test_production_router_retires_teams_and_bridge_cannot_answer_for_human(repository, monkeypatch):
    monkeypatch.setenv('AI_SCIENTIST_AGENT_CONTROL_TOKEN', 'fixture-only-key')
    owner, project, identity, _, _ = setup(repository)
    app = FastAPI()
    app.state.runtime = SimpleNamespace(runtime=owner.gateway)
    app.state.store = owner.projects
    app.state.research_workflows = owner
    app.include_router(importlib.import_module(P+'.api').create_management_router())
    app.include_router(create_n8n_router())
    prefix = '/api/agent-management'
    with TestClient(app, headers={'Authorization': 'Bearer fixture-only-key'}) as browser:
        assert browser.get(prefix+'/identity').status_code == 200
        assert browser.get(prefix+'/agent-presets').status_code == 200
        saved_key = browser.post(prefix+'/literature/key',json={'api_key':'fixture-search-private-key'})
        assert saved_key.status_code == 200 and saved_key.json() == {'configured':True}
        options = browser.get(prefix+'/projects/'+project+'/workflow-options')
        assert options.status_code == 200 and options.json()['literature']['configured']
        assert 'fixture-search-private-key' not in options.text
        assert browser.get(prefix+'/teams').status_code == 404
        assert browser.post(prefix+'/projects/'+project+'/team').status_code == 404
        assert browser.post(prefix+'/pair', json={'rig_ids': [project], 'scopes': ['read']}).status_code == 200
        assert browser.post(prefix+'/n8n/step', json={'project_id': project, 'workflow_id': identity,
            'generation': 1, 'iteration': 0, 'step': 'execution'}).status_code == 401
        pair = browser.post(prefix+'/pair', json={'rig_ids': [project], 'scopes': ['read']}).json()
        browser.post(prefix+'/pair/exchange', json={'pairing_id': pair['pairing_id'], 'code': pair['code'], 'name': 'Read device'})
        browser.headers.pop('Authorization')
        assert browser.get(prefix+'/projects/'+project+'/workflows').status_code == 200
        assert browser.post(prefix+'/literature/key',json={'api_key':'cannot-replace-key'}).status_code == 403
        assert browser.post(prefix+'/projects/'+project+'/workflows/'+identity+'/start').status_code == 403
        assert browser.post(prefix+'/projects/'+project+'/workflows/'+identity+'/inputs/anything',
                            json={'result': {'approve': True, 'reason': 'Read device cannot approve'}}).status_code == 403
        browser.cookies.clear()
        browser.headers['X-Workbench-N8n'] = owner.client.token
        assert browser.post(prefix+'/literature/key',json={'api_key':'cannot-replace-key'}).status_code == 401
        assert browser.post(prefix+'/projects/'+project+'/workflows/'+identity+'/inputs/anything',
                            json={'result': {'approve': True, 'reason': 'Attempt bypass'}}).status_code == 401
        assert browser.post(prefix+'/projects/'+project+'/workflows/'+identity+'/callbacks/retry').status_code == 401
        assert browser.get(prefix+'/devices').status_code == 401
    assert owner.gateway._platform is None


@run_async
async def test_stale_n8n_execution_stops_after_pause_and_restart(repository):
    owner, project, identity, _, _ = setup(repository)
    await owner.start(project, identity)
    generation = owner.store.get(project, identity)['state']['generation']
    await owner.pause(project, identity)
    with pytest.raises(StoreConflict):
        await owner.step(project, identity, generation, 0, 'ideation')
    await owner.start(project, identity)
    owner.recover()
    assert owner.view(project, identity)['state']['status'] == 'PAUSED'
    assert owner.working.admissions == 0
    await owner.close()


@run_async
async def test_team_history_remains_readable_but_cannot_run_or_accept_answers(repository):
    owner, project, identity, _, _ = setup(repository)
    with owner.projects.connection(project) as con:
        con.execute('UPDATE research_workflows SET rig_id=? WHERE id=?', ('old-team', identity))
    row = owner.view(project, identity)
    assert row['archived'] and row['state']['status'] == 'ARCHIVED'
    assert owner.list(project)[0]['id'] == identity
    assert owner.store.get(project, identity)['state']['status'] == 'PAUSED'
    with pytest.raises(StoreConflict, match='Team cũ'):
        await owner.start(project, identity)
    with pytest.raises(StoreConflict, match='Team cũ'):
        owner.current(project, identity)
    assert not owner.client.requests
    await owner.close()


def test_remote_scope_migration_keeps_existing_token_and_never_constructs_teams(repository):
    from ai_scientist.workbench.n8n_migration import migrate_remote_scopes
    owner, project, _, _, _ = setup(repository)
    remote = importlib.import_module(P+'.remote').RemoteDevices(owner.gateway.control_store)
    pair = remote.pairing(scopes=['read', 'research'], rig_ids=['project-'+project])
    device = remote.exchange(pair['pairing_id'], pair['code'], 'Existing device')
    access = importlib.import_module(P+'.auth').DeviceAccess(owner.gateway.control_store)
    before = access.devices()
    migrate_remote_scopes(owner.projects, owner.gateway.control_store)
    after = access.devices()
    assert before[0]['rig_ids'] == ['project-'+project]
    assert after[0]['rig_ids'] == [project]
    assert before[0]['scopes'] == after[0]['scopes']
    with owner.gateway.control_store.connect() as con:
        assert con.execute('SELECT token_hash FROM devices WHERE id=?', (device['device_id'],)).fetchone()[0]
    assert owner.gateway._platform is None
