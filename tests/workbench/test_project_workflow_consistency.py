"""Project tabs share source settings, proposal gates and exact run admission."""
import asyncio
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from ai_scientist.workbench.api import library_router
from ai_scientist.workbench.project_configuration import ProjectConfiguration
from ai_scientist.workbench.research_candidates import generate_candidates, assess_candidates, select_candidate
from ai_scientist.workbench.stage_runtime import StageRuntime
from ai_scientist.workbench.store import ProjectStore, StoreConflict
from ai_scientist.workbench.workflow_models import WorkflowSpec
from tests.workbench.test_n8n_workflows import setup, wait_for, repository


def note(projects, project, title):
    return projects.save_resource(project, {'kind':'text','title':title,'content':title,'url':None})['id']


def test_project_defaults_overrides_restart_and_frozen_proposals(repository):
    owner, project, flow, spec, _ = setup(repository)
    grant_before = owner.store.get(project,flow)['spec']
    settings = ProjectConfiguration(owner.projects)
    a,b = note(owner.projects,project,'First'),note(owner.projects,project,'Second')
    saved = settings.get(project)
    settings.update(project,version=saved['version'],resource_ids=[a])
    idea = owner.projects.save_idea(project,'Checksum','Idea','etc','JSON')['id']
    assert settings.selection(project,idea)['resource_ids']==[a]
    settings.select(project,idea,[b],0)
    snapshot = owner.projects.context_snapshot(project,idea,[b])
    restarted = ProjectConfiguration(ProjectStore(owner.projects.root,repository))
    assert restarted.selection(project,idea)['mode']=='custom'
    assert restarted.selection(project,idea)['resource_ids']==[b]
    settings.update(project,resource_ids=[])
    assert restarted.selection(project,idea)['resource_ids']==[b]
    assert snapshot['snapshot']['resources'][0]['id']==b
    settings.select(project,idea,None,1)
    assert settings.selection(project,idea)['mode']=='inherit'
    assert settings.selection(project,idea)['resource_ids']==[]
    other = owner.projects.create_project('Other')['id']
    with pytest.raises(StoreConflict):
        settings.update(other,resource_ids=[a])
    # New defaults do not modify a previously saved grant.
    assert owner.store.get(project,flow)['spec']==grant_before


def test_shared_idea_commands_advance_n8n_and_cannot_bypass_run_gate(repository):
    async def check():
        owner,project,_,spec,adapter = setup(repository)
        owner.agent_turns.invoke=owner.executor.invoke
        source = note(owner.projects,project,'Context')
        config = owner.controls.configuration
        config.update(project,resource_ids=[source])
        idea = owner.projects.save_idea(project,'Check Unicode checksum','Existing idea','etc','JSON')['id']
        app=FastAPI()
        app.state.store=owner.projects
        app.state.service=owner.planner
        app.state.working=owner.working
        app.state.research_workflows=owner
        app.include_router(library_router(owner.projects,repository))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
            response=await client.post(f'/api/projects/{project}/plan',json={'idea_id':idea,'request_id':uuid.uuid4().hex})
            assert response.status_code==202,response.text
            flow=response.json()['id']
            state=owner.store.get(project,flow)['state']
            assert state['idea_id']==idea and owner.working.admissions==0
            generation=state['generation']
            for phase in ('ideation','literature','idea_selection','proposal'):
                await owner.step(project,flow,generation,0,phase)
                await wait_for(lambda:owner.tasks[(flow,'0:'+phase)].done())
                assert not owner.store.get(project,flow)['state'].get('error')
            assert len(owner.projects.ideas(project))==1
            proposal=owner.projects.proposals(project,idea)[0]
            assert proposal['context_snapshot']['resources'][0]['id']==source
            await owner.step(project,flow,generation,0,'approval')
            await wait_for(lambda:owner.store.get(project,flow)['state']['status']=='WAITING')
            bypass=await client.post(f'/api/projects/{project}/plan',json={'idea_id':idea})
            assert bypass.status_code==409
            edit=await client.put(f'/api/projects/{project}/ideas/{idea}/sources',json={'version':0,'resource_ids':[]})
            assert edit.status_code==409
            approved=await client.post(f'/api/projects/{project}/proposals/{proposal["id"]}/approve',json={'version':proposal['version'],'context_sha256':proposal['context_sha256']})
            assert approved.status_code==200 and approved.json()['workflow_id']==flow
            await wait_for(lambda:owner.tasks[(flow,'0:approval')].done())
            state=owner.store.get(project,flow)['state']
            assert owner.working.admissions==0 and state['run_id']
            run=state['run_id']
            await owner.step(project,flow,generation,0,'run_approval')
            await wait_for(lambda:owner.store.get(project,flow)['state']['status']=='WAITING')
            wrong=await client.post(f'/api/projects/{project}/runs/{run}/working',json={'account':'different','accelerator':'cpu','ttl_seconds':180})
            assert wrong.status_code==409 and owner.working.admissions==0
            configured=(await client.get(f'/api/projects/{project}/runs/{run}/configuration')).json()
            stale=await client.post(f'/api/projects/{project}/runs/{run}/start',json={'version':configured['version']+1,'configuration':configured['configuration']})
            assert stale.status_code==409 and owner.working.admissions==0
            approved=await client.post(f'/api/projects/{project}/runs/{run}/start',json={'version':configured['version'],'configuration':configured['configuration']})
            assert approved.status_code==202 and approved.json()['workflow_id']==flow
            await wait_for(lambda:owner.tasks[(flow,'0:run_approval')].done())
            await owner.step(project,flow,generation,0,'execution')
            await wait_for(lambda:owner.tasks[(flow,'0:execution')].done())
            assert owner.working.admissions==1
            repeated=await client.post(f'/api/projects/{project}/runs/{run}/working',json={'account':spec.account,'accelerator':spec.accelerator,'ttl_seconds':spec.ttl_seconds})
            assert repeated.status_code==409 and owner.working.admissions==1
        await owner.close()
    asyncio.run(check())


def test_resume_from_run_pins_variant_baseline_and_feeds_previous_result(repository):
    async def check():
        from ai_scientist.workbench.run_view import RunView
        owner,project,flow,spec,_=setup(repository)
        owner.planner.view=RunView(owner.projects,repository,lambda:False)
        idea=owner.projects.save_idea(project,'Original checksum','Original','etc','JSON')['id']
        body={'needs_clarification':False,'questions':[],'paraphrase':'Original','objective':'Original',
              'implementation_steps':['Checksum'],'data_refs':[],'expected_outputs':['JSON'],
              'budget':{'execution_seconds':60,'output_bytes':1000},'research':None}
        owner.projects.save_proposal(project,idea,body,owner.projects.context_snapshot(project,idea,[]))
        proposal=owner.projects.proposals(project,idea)[0]
        run=await owner.planner.approve(project,proposal['id'],proposal['version'],proposal['context_sha256'])
        with owner.projects.connection(project) as con:
            con.execute("UPDATE runs SET state='COMPLETED' WHERE id=?",(run['id'],))
        copied=spec.model_copy(deep=True)
        copied.stages['ideation'].actor='agent'
        copied.stages['ideation'].preset_id='default'
        identity=uuid.uuid4().hex
        owner.create(project,identity,copied)
        await owner.start(project,identity,from_run_id=run['id'])
        runtime=StageRuntime(owner,project,identity)
        prompts=[]
        def invoke(stage,prompt,schema,**kwargs):
            prompts.append(prompt)
            return {'title':'Improve checksum','text':'Test an alternate checksum approach'}
        runtime.invoke=invoke
        await generate_candidates(runtime)
        assert prompts[0]['previous_result']['run_id']==run['id']
        await assess_candidates(runtime)
        await select_candidate(runtime)
        selected=owner.store.get(project,identity)['state']['idea_id']
        assert owner.projects.idea(project,selected)['variant']['parent_run_id']==run['id']
        context=owner.projects.context_snapshot(project,selected,[])
        assert context['snapshot']['variant']['baseline']['parent']['run_id']==run['id']
        await owner.close()
    asyncio.run(check())


def test_human_selects_saved_idea_and_context_is_frozen_before_agent(repository):
    async def check():
        owner,project,flow,_,_=setup(repository)
        idea=owner.projects.save_idea(project,'Checksum','Human idea','etc','JSON')['id']
        source=note(owner.projects,project,'Idea-only source')
        owner.controls.configuration.select(project,idea,[source],0)
        await owner.start(project,flow)
        runtime=StageRuntime(owner,project,flow)
        task=asyncio.create_task(generate_candidates(runtime))
        pending=await wait_for(lambda:next((i for i in owner.store.inputs(project,flow) if i['state']=='PENDING'),None))
        owner.controls.choose_idea(project,flow,pending['id'],idea)
        # The gate and selected context commit atomically before waking n8n.
        row=owner.store.get(project,flow)
        assert row['state']['idea_id']==idea and row['spec']['resource_ids']==[source]
        assert owner.store.inputs(project,flow)[0]['state']=='DONE'
        with pytest.raises(StoreConflict):
            owner.controls.configuration.select(project,idea,[],1)
        await task
        await assess_candidates(runtime)
        await select_candidate(runtime)
        assert owner.store.get(project,flow)['state']['idea_id']==idea
        assert len(owner.projects.ideas(project))==1
        await owner.close()
    asyncio.run(check())
