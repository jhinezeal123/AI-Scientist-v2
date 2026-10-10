"""No paid providers: verify delegation, human handoffs and real bridge mediation."""
import asyncio
import json
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
import uuid
from functools import wraps
import pytest
from ai_scientist.workbench.agents.contracts import RuntimeRequest, RuntimeCancelled
from ai_scientist.workbench.models import SearchOptions
from ai_scientist.workbench.research_workflows import ResearchWorkflows
from ai_scientist.workbench.service import PlanningService
from ai_scientist.workbench.stage_runtime import StageRuntime
from ai_scientist.workbench.store import ProjectStore, StoreConflict
from ai_scientist.workbench.worker import RuntimeWorker
from ai_scientist.workbench.workflow_models import STAGES, WorkflowSpec
from ai_scientist.workbench.ssh_terminal import AgentTerminalBridge
from tests.workbench.test_agent_team_api import client, repository

def run_async(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))
    return wrapped

class FixturePlatform:
    def __init__(self, project):
        self.tasks, self.active, self.lock, self.messages = [], {}, RLock(), []
        self.rig = SimpleNamespace(project_id=project, seats=[SimpleNamespace(id=s,harness='fixture') for s in STAGES])
        self.registry = SimpleNamespace(resolve=lambda _:SimpleNamespace(probe=lambda:{'ready':True}))
        self.store = SimpleNamespace(rig=lambda _: self.rig, snapshot=lambda _: {'tasks': self.tasks})
        self.answer = None
    def start(self, _):
        pass
    def enqueue(self, rig, seat, request_id, request):
        message = json.loads(request.instruction)
        self.messages.append(message)
        stage = message['stage']
        payload = ({'title': 'Checksum experiment', 'text': 'Verify checksum correctness'} if stage == 'ideation'
                   else {'approve': True, 'reason': 'Within the explicit operator grant'} if stage == 'approval'
                   else {'needs_clarification': False, 'questions': [], 'paraphrase': 'Verify checksum correctness',
                         'objective': 'Verify checksum correctness', 'implementation_steps': ['Execute checksum cases'],
                         'data_refs': [], 'budget': {'execution_seconds': 60, 'output_bytes': 1000}})
        if self.answer:
            payload = self.answer(message)
        task = {'id': uuid.uuid4().hex, 'state': 'DONE', 'result': {'summary': json.dumps(payload), 'files': []}}
        self.tasks.append(task)
        return task

class FixtureWorking:
    def __init__(self, projects):
        self.accounts, self.projects, self.records, self.admissions = None, projects, {}, 0
        self.view = SimpleNamespace(root=lambda p,r: projects.run_root(p,r))
    def record(self, project, run):
        return self.records.get((project,run))
    def detail(self, project, run):
        return {'state': self.projects.run(project,run)['state'], 'output': {'summary': 'verified fixture'}}
    async def start(self, project, run, **kwargs):
        self.admissions += 1
        self.records[(project,run)] = {'stop_confirmed': True}
        with self.projects.connection(project) as con:
            con.execute("UPDATE runs SET state='COMPLETED' WHERE id=?", (run,))
    async def stop(self, project, run):
        self.records[(project,run)]['stop_confirmed'] = True

def setup(tmp_path, *, approval='agent', calls=10):
    from ai_scientist.workbench.runtime import _agent_gateway_class
    _agent_gateway_class()
    projects = ProjectStore(tmp_path/'projects', tmp_path)
    project = projects.create_project('Workflow fixture')['id']
    platform = FixturePlatform(project)
    gateway = SimpleNamespace(platform=platform)
    worker = RuntimeWorker(SimpleNamespace(run=lambda *args: None), tmp_path/'legacy-state.json')
    planner = PlanningService(projects, SimpleNamespace(request_type=RuntimeRequest), worker, tmp_path)
    working = FixtureWorking(projects)
    owner = ResearchWorkflows(planner, working, gateway)
    spec = WorkflowSpec(goal='Verify checksum correctness', mode='etc', desired_output='A checksum result JSON',
        account='fixture', execution_seconds=60, ttl_seconds=180, output_bytes=1000,
        max_agent_calls=calls, stages={s:{'seat':s,'actor':approval if s=='approval' else 'agent'} for s in STAGES},
        allow_agent_approval=approval=='agent', search=SearchOptions(enabled=False))
    identity = uuid.uuid4().hex
    owner.create('rig', identity, spec)
    return owner, identity, project, spec

@run_async
async def test_full_auto_uses_each_stage_and_admits_once(tmp_path):
    owner, identity, project, _ = setup(tmp_path)
    await owner.start('rig', identity)
    await asyncio.wait_for(owner.tasks[identity], 5)
    row = owner.view('rig', identity)
    assert row['state']['status']=='DONE', row['state']
    assert owner.working.admissions == 1
    assert [m['stage'] for m in owner.gateway.platform.messages]==['ideation','proposal','approval']
    assert row['state']['approvals'][0]['actor']=='agent'
    assert row['state']['approvals'][0]['grant_id']==row['state']['grant_id']
    assert len(row['state']['runs'])==1
    owner.recover()
    with pytest.raises(StoreConflict):
        await owner.start('rig', identity)
    assert owner.working.admissions==1
    await owner.close()

@run_async
async def test_human_approval_waits_without_admission(tmp_path):
    owner, identity, project, _ = setup(tmp_path, approval='human')
    await owner.start('rig', identity)
    for _ in range(100):
        inputs=owner.store.inputs(project,identity)
        if inputs:
            break
        await asyncio.sleep(.02)
    assert inputs[0]['stage']=='approval'
    assert owner.working.admissions==0
    owner.store.answer(project,identity,inputs[0]['id'],{'approve':True,'reason':'Human reviewed this exact proposal'})
    await asyncio.wait_for(owner.tasks[identity],5)
    assert owner.store.get(project,identity)['state']['status']=='DONE'
    assert owner.store.get(project,identity)['state']['approvals'][0]['actor']=='human'
    await owner.close()

@run_async
async def test_exhausted_call_budget_cannot_approve_or_submit(tmp_path):
    owner, identity, project, _=setup(tmp_path,calls=1)
    await owner.start('rig',identity)
    await asyncio.wait_for(owner.tasks[identity],5)
    assert owner.store.get(project,identity)['state']['status']=='PAUSED'
    assert owner.working.admissions==0
    assert len(owner.gateway.platform.messages)==1
    await owner.close()

def test_grant_is_immutable_and_approval_budget_is_enforced(tmp_path):
    owner, identity, project, spec=setup(tmp_path)
    assert owner.create('rig',identity,spec)['id']==identity
    with pytest.raises(StoreConflict):
        owner.create('rig',identity,spec.model_copy(update={'goal':'Different goal'}))
    body={'needs_clarification':False,'questions':[],'paraphrase':'scope','objective':'scope',
          'implementation_steps':['execute'],'budget':{'execution_seconds':61,'output_bytes':1000}}
    with pytest.raises(StoreConflict):
        owner.check_budget(spec,body)
    with pytest.raises(ValueError):
        WorkflowSpec.model_validate({**spec.model_dump(),'allow_agent_approval':False})

def test_pause_rejects_stage_before_queueing(tmp_path):
    owner, identity, project, _=setup(tmp_path)
    runtime=StageRuntime(owner,project,identity)
    with pytest.raises(RuntimeCancelled):
        runtime.invoke('ideation',{}, {'type':'object'})
    assert owner.gateway.platform.messages==[]

def test_tool_free_harness_actions_reach_existing_terminal_bridge(tmp_path):
    owner, identity, project, _=setup(tmp_path)
    owner.store.change(project,identity,lambda s:s.update(status='RUNNING'))
    workdir=tmp_path/'working'
    commands=[]
    terminal=SimpleNamespace(request=lambda action,**kw: {'returncode':0,'text':'4/4 assertions passed'})
    bridge=AgentTerminalBridge(terminal,workdir,on_command=commands.append)
    secret=bridge.token
    def respond(message):
        if len(owner.gateway.platform.messages)==1:
            return {'action':'exec','command':'python source/checksum.py','timeout':2}
        return {'action':'finish','result':{'succeeded':True,'summary':'verified','limitations':[],'output_files':[]}}
    owner.gateway.platform.answer=respond
    try:
        result=StageRuntime(owner,project,identity).run(RuntimeRequest('run','mvp0_working','Do checksum',workdir,timeout_seconds=5),lambda _:None,lambda:False)
    finally:
        bridge.close()
    assert json.loads(result.text)['succeeded']
    assert len(commands)==1 and commands[0]['command']=='python source/checksum.py'
    assert secret not in json.dumps(owner.gateway.platform.messages)

def test_scoped_agents_cannot_delegate_approve_or_read_other_stage_inputs(client,tmp_path):
    browser,gateway=client
    owner,identity,project,spec=setup(tmp_path)
    import importlib
    models=importlib.import_module(gateway.__module__.rsplit('.',1)[0]+'.models')
    rig=next(t for t in models.templates() if t['template']=='research')
    rig['project_id']=project
    browser.app.state.store=owner.projects
    assert browser.post('/api/agent-management/teams',json={'id':'research-team','spec':rig}).status_code==200
    owner.gateway=gateway
    browser.app.state.store=owner.projects
    browser.app.state.research_workflows=owner
    from ai_scientist.workbench.workflow_api import create_workflow_router
    browser.app.include_router(create_workflow_router())
    base='/api/agent-management/teams/research-team'
    request_id=uuid.uuid4().hex
    created=browser.post(base+'/workflows',json={'request_id':request_id,'spec':spec.model_dump()})
    assert created.status_code==200,created.text
    credential=browser.post(base+'/seats/ideation/credential').json()['token']
    headers={'Authorization':'Bearer '+credential}
    assert browser.post(base+'/workflows',json={'request_id':uuid.uuid4().hex,'spec':spec.model_dump()},headers=headers).status_code==403
    assert browser.post(base+'/workflows/'+request_id+'/start',headers=headers).status_code==403
    assert browser.get(base+'/workflows/'+request_id,headers=headers).status_code==403

@run_async
async def test_invalid_human_verdict_cannot_resume_or_consume_input(tmp_path):
    owner,identity,project,_=setup(tmp_path,approval='human')
    await owner.start('rig',identity)
    for _ in range(100):
        inputs=owner.store.inputs(project,identity)
        if inputs:
            break
        await asyncio.sleep(.02)
    with pytest.raises(ValueError):
        owner.store.answer(project,identity,inputs[0]['id'],{'approve':'false','reason':'invalid boolean'})
    assert owner.store.inputs(project,identity)[0]['state']=='PENDING'
    assert owner.working.admissions==0
    await owner.close()

@run_async
async def test_pause_resume_keeps_the_same_human_approval_and_old_actor_stops(tmp_path):
    owner,identity,project,_=setup(tmp_path,approval='human')
    await owner.start('rig',identity)
    for _ in range(100):
        inputs=owner.store.inputs(project,identity)
        if inputs:
            break
        await asyncio.sleep(.02)
    first=inputs[0]['id']
    old_runtime=StageRuntime(owner,project,identity)
    await owner.pause('rig',identity)
    with pytest.raises(StoreConflict):
        owner.store.answer(project,identity,first,{'approve':True,'reason':'paused'})
    await owner.start('rig',identity)
    with pytest.raises(RuntimeCancelled):
        old_runtime.check()
    for _ in range(100):
        if owner.store.get(project,identity)['state']['status']=='WAITING':
            break
        await asyncio.sleep(.02)
    assert [v['id'] for v in owner.store.inputs(project,identity)]==[first]
    assert len(owner.gateway.platform.messages)==2
    owner.store.answer(project,identity,first,{'approve':True,'reason':'approve preserved candidate'})
    await asyncio.wait_for(owner.tasks[identity],5)
    assert owner.working.admissions==1
    assert owner.store.get(project,identity)['state']['status']=='DONE'
    await owner.close()

@run_async
async def test_ask_review_resumes_without_regenerating_agent_candidate(tmp_path):
    owner,identity,project,spec=setup(tmp_path)
    spec.stages['ideation'].ask=True
    identity=uuid.uuid4().hex
    owner.create('rig',identity,spec)
    await owner.start('rig',identity)
    for _ in range(100):
        inputs=owner.store.inputs(project,identity)
        if inputs:
            break
        await asyncio.sleep(.02)
    first=inputs[0]['id']
    await owner.pause('rig',identity)
    await owner.start('rig',identity)
    for _ in range(100):
        if owner.store.get(project,identity)['state']['status']=='WAITING':
            break
        await asyncio.sleep(.02)
    assert len(owner.gateway.platform.messages)==1
    assert owner.store.inputs(project,identity)[0]['id']==first
    owner.store.answer(project,identity,first,{'approve':True,'reason':'same result'})
    await asyncio.wait_for(owner.tasks[identity],5)
    assert owner.store.get(project,identity)['state']['status']=='DONE'
    await owner.close()

@run_async
async def test_selected_library_is_available_to_stage_actors_and_stale_grant_stops(tmp_path):
    owner,_,project,spec=setup(tmp_path)
    source=owner.projects.save_resource(project,{'title':'Pinned hypothesis','content':'Selected source marker 0192','url':None,'kind':'text'})
    spec=spec.model_copy(update={'resource_ids':[source['id']]})
    identity=uuid.uuid4().hex
    owner.create('rig',identity,spec)
    await owner.start('rig',identity)
    await asyncio.wait_for(owner.tasks[identity],5)
    assert owner.store.get(project,identity)['state']['status']=='DONE'
    assert all('Selected source marker 0192' in json.dumps(m['input']['selected_library']) for m in owner.gateway.platform.messages)
    identity=uuid.uuid4().hex
    owner.create('rig',identity,spec)
    owner.projects.save_resource(project,{'title':'Pinned hypothesis','content':'Changed source','url':None,'kind':'text'},source['id'],1)
    before=len(owner.gateway.platform.messages)
    await owner.start('rig',identity)
    await asyncio.wait_for(owner.tasks[identity],5)
    assert owner.store.get(project,identity)['state']['status']=='PAUSED'
    assert len(owner.gateway.platform.messages)==before
    assert owner.working.admissions==1
    await owner.close()

@run_async
async def test_human_can_write_proposal_without_an_agent_planner(tmp_path):
    owner,_,project,spec=setup(tmp_path)
    spec.stages['proposal'].actor='human'
    identity=uuid.uuid4().hex
    owner.create('rig',identity,spec)
    await owner.start('rig',identity)
    for _ in range(100):
        inputs=owner.store.inputs(project,identity)
        if inputs:
            break
        await asyncio.sleep(.02)
    assert inputs[0]['stage']=='proposal'
    owner.store.answer(project,identity,inputs[0]['id'],{'needs_clarification':False,'questions':[],
        'paraphrase':'Human proposal','objective':'Verify checksum correctness','implementation_steps':['Execute checksum cases'],
        'data_refs':[], 'expected_outputs':['result.json'],'budget':{'execution_seconds':60,'output_bytes':1000},'research':None})
    await asyncio.wait_for(owner.tasks[identity],5)
    assert owner.store.get(project,identity)['state']['status']=='DONE'
    assert [m['stage'] for m in owner.gateway.platform.messages]==['ideation','approval']
    assert owner.working.admissions==1
    await owner.close()

@run_async
async def test_missing_stage_harness_is_rejected_before_model_or_kaggle(tmp_path):
    owner,identity,project,_=setup(tmp_path)
    owner.gateway.platform.registry=SimpleNamespace(resolve=lambda _:SimpleNamespace(probe=lambda:{'ready':False}))
    with pytest.raises(StoreConflict):
        await owner.start('rig',identity)
    assert owner.working.admissions==0
    assert owner.gateway.platform.messages==[]
    assert owner.store.get(project,identity)['state']['status']=='PAUSED'
    await owner.close()

@run_async
async def test_human_proposal_pause_closes_worker_and_reuses_input(tmp_path):
    owner,_,project,spec=setup(tmp_path)
    spec.stages['proposal'].actor='human'
    identity=uuid.uuid4().hex
    owner.create('rig',identity,spec)
    await owner.start('rig',identity)
    for _ in range(100):
        inputs=owner.store.inputs(project,identity)
        if inputs:
            break
        await asyncio.sleep(.02)
    first=inputs[0]['id']
    await owner.pause('rig',identity)
    await owner.start('rig',identity)
    for _ in range(100):
        if owner.store.get(project,identity)['state']['status']=='WAITING':
            break
        await asyncio.sleep(.02)
    assert [i['id'] for i in owner.store.inputs(project,identity)]==[first]
    owner.store.answer(project,identity,first,{'needs_clarification':False,'questions':[],
        'paraphrase':'Human proposal','objective':'Verify checksum correctness','implementation_steps':['Execute checksum cases'],
        'data_refs':[], 'budget':{'execution_seconds':60,'output_bytes':1000}})
    await asyncio.wait_for(owner.tasks[identity],5)
    assert owner.store.get(project,identity)['state']['status']=='DONE'
    assert owner.working.admissions==1
    await owner.close()

@run_async
async def test_unknown_planner_requires_owned_session_reconciliation(tmp_path):
    owner,identity,project,_=setup(tmp_path)
    platform=owner.gateway.platform
    enqueue=platform.enqueue
    def uncertain(rig,seat,request_id,request):
        task=enqueue(rig,seat,request_id,request)
        if seat=='proposal':
            task['state']='UNKNOWN'
        return task
    platform.enqueue=uncertain
    await owner.start('rig',identity)
    await asyncio.wait_for(owner.tasks[identity],5)
    assert owner.store.get(project,identity)['state']['status']=='UNKNOWN'
    assert owner.working.admissions==0
    with pytest.raises(StoreConflict):
        await owner.start('rig',identity)
    with pytest.raises(StoreConflict):
        await owner.reconcile('rig',identity)
    platform.tasks[-1]['state']='FAILED'
    platform.enqueue=enqueue
    await owner.reconcile('rig',identity)
    await owner.start('rig',identity)
    await asyncio.wait_for(owner.tasks[identity],5)
    assert owner.store.get(project,identity)['state']['status']=='DONE'
    assert owner.working.admissions==1
    await owner.close()

@run_async
async def test_concurrent_start_requests_have_only_one_workflow_driver(tmp_path):
    owner,identity,project,_=setup(tmp_path)
    await asyncio.gather(owner.start('rig',identity),owner.start('rig',identity))
    await asyncio.wait_for(owner.tasks[identity],5)
    assert owner.store.get(project,identity)['state']['status']=='DONE'
    assert owner.working.admissions==1
    assert [m['stage'] for m in owner.gateway.platform.messages]==['ideation','proposal','approval']
    await owner.close()
