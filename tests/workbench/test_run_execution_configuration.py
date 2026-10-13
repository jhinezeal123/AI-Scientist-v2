"""Hybrid chooses per-run resources; frozen grants and approval scope stay intact."""
import asyncio
import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from ai_scientist.workbench.api import library_router
from ai_scientist.workbench.models import SearchOptions
from ai_scientist.workbench.project_configuration import ProjectConfiguration
from ai_scientist.workbench.run_configuration import RunConfiguration
from ai_scientist.workbench.run_execution_configuration import RunExecutionConfigurations
from ai_scientist.workbench.stage_runtime import StageRuntime
from ai_scientist.workbench.store import ProjectStore, StoreConflict
from ai_scientist.workbench.workflow_models import WorkflowSpec
from tests.workbench.test_n8n_workflows import setup, wait_for, repository


def approved_run(owner, project, title='Run', requirements=None):
    idea = owner.projects.save_idea(project, 'Check checksum', title, 'etc', 'JSON')['id']
    context = owner.projects.context_snapshot(project, idea, [])
    body = {'needs_clarification':False,'questions':[],'paraphrase':'Checksum','objective':'Checksum',
        'implementation_steps':['Check checksum'],'data_refs':[],'expected_outputs':['JSON'],
        'budget':{'execution_seconds':60,'output_bytes':1000}}
    if requirements:
        body['execution_requirements']=requirements
    proposal = owner.projects.save_proposal(project, idea, body, context)
    candidate = owner.projects.proposals(project, idea)[0]
    return owner.projects.approve_proposal(project, candidate['id'], candidate['version'], candidate['context_sha256'])['id']


async def hybrid_run(owner, project, spec):
    owner.agent_turns.invoke = owner.executor.invoke
    identity = uuid.uuid4().hex
    spec = WorkflowSpec.model_validate({**spec.model_dump(), 'run_setup':'per_run','account':''})
    owner.create(project, identity, spec)
    idea = owner.projects.save_idea(project, 'Check checksum', 'Hybrid', 'etc', 'JSON')['id']
    await owner.start(project, identity, idea_id=idea)
    generation = owner.store.get(project, identity)['state']['generation']
    for phase in ('ideation','literature','idea_selection','proposal'):
        await owner.step(project, identity, generation, 0, phase)
        await wait_for(lambda: owner.tasks[(identity,'0:'+phase)].done())
        assert not owner.store.get(project, identity)['state'].get('error')
    await owner.step(project, identity, generation, 0, 'approval')
    gate = await wait_for(lambda:next((v for v in owner.store.inputs(project,identity) if v['state']=='PENDING'),None))
    owner.store.answer(project,identity,gate['id'],{'approve':True,'reason':'Reviewed proposal'})
    await wait_for(lambda:owner.tasks[(identity,'0:approval')].done())
    run = owner.store.get(project,identity)['state']['run_id']
    await owner.step(project,identity,generation,0,'run_approval')
    await wait_for(lambda:owner.store.get(project,identity)['state']['status']=='WAITING')
    return identity, generation, run


def test_run_defaults_have_no_scientific_fields_and_drafts_survive_restart(repository):
    owner,project,flow,spec,_=setup(repository)
    settings=owner.controls.configuration
    before=owner.store.get(project,flow)['spec']
    saved=settings.get(project)
    assert not {'mode','benchmark_id','desired_output','research','goal'} & set(saved['run'])
    assert saved['idea']['mode']=='etc'
    first=approved_run(owner,project,'First')
    runs=owner.run_admission.configurations
    original=runs.get(project,first)
    draft=RunConfiguration.model_validate({**original['configuration'],'account':'first','accelerator':'NvidiaT4'})
    changed=runs.commit(project,first,original['version'],draft)
    with pytest.raises(StoreConflict):
        runs.commit(project,first,original['version'],draft)
    settings.save_run(project,saved['version'],RunConfiguration.model_validate({**saved['run'],'account':'later','ttl_seconds':600}))
    restarted=RunExecutionConfigurations(ProjectStore(owner.projects.root,repository))
    assert restarted.get(project,first)['configuration']==changed['configuration']
    second=approved_run(owner,project,'Second')
    assert restarted.get(project,second)['configuration']['account']=='later'
    owner.run_admission.save(project,first,changed['version'],draft,remember=True)
    assert settings.get(project)['run']['account']=='first'
    assert restarted.get(project,second)['configuration']['account']=='later'
    assert owner.store.get(project,flow)['spec']==before
    with pytest.raises(KeyError):
        restarted.get(owner.projects.create_project('Other')['id'],first)
    asyncio.run(owner.close())


def test_hybrid_can_save_without_account_benchmark_or_scope_until_idea_is_selected(repository):
    owner,project,_,spec,_=setup(repository)
    scope=WorkflowSpec.model_validate({**spec.model_dump(),'mode':'training_research','benchmark_id':None,
        'desired_output':'','account':'','run_setup':'per_run'})
    flow=uuid.uuid4().hex
    owner.create(project,flow,scope)
    assert owner.store.get(project,flow)['spec']['account']==''
    with pytest.raises(ValueError):
        WorkflowSpec.model_validate({**scope.model_dump(),'require_run_approval':False})
    with pytest.raises(ValueError):
        RunConfiguration.model_validate({**owner.controls.configuration.get(project)['run'],'mode':'etc'})
    asyncio.run(owner.close())


def test_existing_run_configuration_migrates_atomically_and_repairs_interrupted_backfill(repository):
    owner,project,_,_,_=setup(repository)
    run=approved_run(owner,project)
    configurations=owner.run_admission.configurations
    before=configurations.get(project,run)
    with owner.projects.connection(project) as con:
        con.execute('ALTER TABLE run_execution_configuration DROP COLUMN planned_search_json')
    migrated=configurations.get(project,run)
    assert migrated['configuration']==before['configuration']
    assert migrated['version']==before['version']
    assert migrated['planned_search']==before['planned_search']
    with owner.projects.connection(project) as con:
        con.execute('UPDATE run_execution_configuration SET planned_search_json=NULL')
    assert configurations.get(project,run)==migrated
    asyncio.run(owner.close())


def test_hybrid_admission_pins_selected_resources_and_retries_do_not_admit_twice(repository):
    async def check():
        owner,project,_,spec,_=setup(repository)
        identity,generation,run=await hybrid_run(owner,project,spec)
        frozen=owner.store.get(project,identity)['spec']
        value=owner.run_admission.configurations.get(project,run)
        config=RunConfiguration.model_validate({**value['configuration'],'account':'chosen','accelerator':'NvidiaT4','ttl_seconds':300})
        payload={'version':value['version'],'configuration':config.model_dump(mode='json'),'remember_defaults':True}
        app=FastAPI();app.state.store=owner.projects;app.state.working=owner.working;app.state.research_workflows=owner
        app.include_router(library_router(owner.projects,repository))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
            rejected=await client.post(f'/api/projects/{project}/runs/{run}/start',json={**payload,'version':value['version']+1})
            assert rejected.status_code==409 and owner.working.admissions==0
            result=await client.post(f'/api/projects/{project}/runs/{run}/start',json=payload)
            assert result.status_code==202,result.text
            assert owner.working.admissions==0
            assert (await client.post(f'/api/projects/{project}/runs/{run}/start',json=payload)).status_code==202
        await wait_for(lambda:owner.tasks[(identity,'0:run_approval')].done())
        runtime=StageRuntime(owner,project,identity)
        assert (runtime.spec.account,runtime.spec.accelerator,runtime.spec.ttl_seconds)==('chosen','NvidiaT4',300)
        assert owner.store.get(project,identity)['spec']==frozen
        await owner.step(project,identity,generation,0,'execution')
        await wait_for(lambda:owner.tasks[(identity,'0:execution')].done())
        assert owner.working.admissions==1
        await owner.run_admission.start(project,run,value['version'],config)
        assert owner.working.admissions==1
        with pytest.raises(StoreConflict):
            owner.run_admission.configurations.commit(project,run,value['version']+1,config.model_copy(update={'account':'other'}))
        assert owner.controls.configuration.get(project)['run']['account']=='chosen'
        await owner.close()
    asyncio.run(check())


def test_budget_and_search_changes_require_a_new_proposal_and_replan_is_idempotent(repository):
    async def check():
        owner,project,_,spec,_=setup(repository)
        identity,_,run=await hybrid_run(owner,project,spec)
        saved=owner.run_admission.configurations.get(project,run)
        config=RunConfiguration.model_validate({**saved['configuration'],'execution_seconds':120,'ttl_seconds':300})
        before=owner.projects.approved_snapshot(project,run)
        defaults_before=owner.controls.configuration.get(project)
        with pytest.raises(StoreConflict,match='proposal'):
            await owner.run_admission.start(project,run,saved['version'],config.model_copy(update={'account':'chosen'}))
        reply=await owner.run_admission.replan(project,run,saved['version'],config)
        assert owner.working.admissions==0
        assert owner.projects.run(project,run)['state']=='CANCELLED'
        assert owner.store.get(project,identity)['state']['status']=='CANCELLED'
        new=owner.store.get(project,reply['workflow_id'])
        assert new['spec']['execution_seconds']==120 and new['state']['idea_id']==reply['idea_id']
        assert owner.projects.approved_snapshot(project,run)==before
        assert owner.controls.configuration.get(project)==defaults_before
        assert await owner.run_admission.replan(project,run,saved['version'],config)==reply
        assert len(owner.projects.ideas(project))==2
        assert owner.projects.idea(project,reply['idea_id'])['mode']=='etc'
        await owner.close()
    asyncio.run(check())


def test_full_agent_uses_its_frozen_execution_policy(repository):
    owner,project,_,spec,_=setup(repository)
    spec=WorkflowSpec.model_validate({**spec.model_dump(),'run_setup':'per_run','require_run_approval':False})
    identity=uuid.uuid4().hex;owner.create(project,identity,spec)
    run=approved_run(owner,project)
    owner.store.change(project,identity,lambda s:s.update(run_id=run,status='RUNNING'))
    saved=owner.controls.configuration.get(project)
    owner.controls.configuration.save_run(project,saved['version'],RunConfiguration.model_validate({**saved['run'],'account':'changed-after-grant','accelerator':'NvidiaT4'}))
    value=owner.run_admission.delegated(StageRuntime(owner,project,identity))
    assert value['approved'] and value['configuration']['account']==spec.account and value['configuration']['accelerator']==spec.accelerator
    asyncio.run(owner.close())


def test_hardware_contract_and_worker_limits_preserve_original_proposal(repository):
    from ai_scientist.workbench.working import WorkingService
    owner,project,_,_,_=setup(repository)
    run=approved_run(owner,project,requirements={'accelerators':['NvidiaT4'],'reason':'CUDA is required'})
    runs=owner.run_admission.configurations
    value=runs.get(project,run)
    config=RunConfiguration.model_validate({**value['configuration'],'account':'chosen','execution_seconds':30,'output_bytes':500})
    with pytest.raises(StoreConflict,match='Accelerator'):
        runs.commit(project,run,value['version'],config,approve=True)
    config.accelerator='NvidiaT4'
    runs.commit(project,run,value['version'],config,approve=True)
    before=owner.projects.approved_snapshot(project,run)
    worker=WorkingService.__new__(WorkingService);worker.store=owner.projects
    effective=worker._execution_context(project,run,before)
    assert effective['body']['budget']=={'execution_seconds':30,'output_bytes':500}
    assert effective['execution_configuration']['accelerator']=='NvidiaT4'
    assert owner.projects.approved_snapshot(project,run)==before
    asyncio.run(owner.close())


def test_manual_batch_admits_each_run_with_its_own_configuration(repository):
    async def check():
        owner,project,_,_,_=setup(repository)
        runs=[approved_run(owner,project,'One'),approved_run(owner,project,'Two')]
        calls=[]
        original=owner.working.start
        async def start(project,run,**kwargs):
            calls.append((run,kwargs['account'],kwargs['accelerator']))
            return await original(project,run,**kwargs)
        owner.working.start=start
        items=[]
        for run,account,accelerator in zip(runs,['one','two'],['cpu','NvidiaT4']):
            saved=owner.run_admission.configurations.get(project,run)
            items.append({'run_id':run,'version':saved['version'],'configuration':{
                **saved['configuration'],'account':account,'accelerator':accelerator}})
        app=FastAPI();app.state.working=owner.working;app.state.research_workflows=owner
        app.include_router(library_router(owner.projects,repository))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
            result=await client.post(f'/api/projects/{project}/runs/batch',json={'runs':items})
            assert result.status_code==202,result.text
            assert all(item['state']=='COMPLETED' for item in result.json()['runs'])
        assert calls==[(runs[0],'one','cpu'),(runs[1],'two','NvidiaT4')]
        assert owner.working.admissions==2
        await owner.close()
    asyncio.run(check())
