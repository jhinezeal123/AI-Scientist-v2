"""Human-triggered replanning, clarification locks and exact-version approvals."""
import asyncio
import json
from types import SimpleNamespace
import uuid

import pytest

from ai_scientist.workbench.store import StoreConflict
from ai_scientist.workbench.run_phases import RUN_PHASES
from tests.workbench.test_n8n_workflows import setup, wait_for, FixtureAdapter, repository
from tests.workbench.test_stage_workflows import run_async


@run_async
@pytest.mark.parametrize('ambiguous', [False, True])
async def test_only_human_messages_replan_and_old_approval_cannot_be_reused(repository, ambiguous):
    owner, project, identity, _, _ = setup(repository)
    contexts=[]
    class Planner(FixtureAdapter):
        def send(self, handle, message, **kwargs):
            contexts.append(json.loads(message)['input']['workspace_files']['context.json']['snapshot']['idea']['conversation'])
            if ambiguous and len(contexts)==1:
                handle.stop_receipt={'tree_stopped':True,'process_exited':True}
                return SimpleNamespace(result=SimpleNamespace(summary=json.dumps({
                    'needs_clarification':True,'questions':['Which checksum cases should be tested?'],
                    'paraphrase':'Checksum scope is ambiguous'}),files=[]),receipt=handle.stop_receipt)
            return super().send(handle,message,**kwargs)
    owner.gateway._harness_catalog.resolve=lambda _:Planner()
    owner.agent_turns.invoke=owner.executor.invoke
    await owner.start(project,identity)
    generation=owner.store.get(project,identity)['state']['generation']
    async def call(stage, round=0):
        return await owner.step(project,identity,generation,0,stage,proposal_round=round)
    async def done(stage, round=0):
        key=owner.step_key(0,stage,round)
        await wait_for(lambda: owner.tasks[(identity,key)].done())
        result=await call(stage,round)
        assert not result['failed'],result
        return result
    async def input(stage):
        return await wait_for(lambda: next((v for v in owner.store.inputs(project,identity)
                                            if v['stage']==stage and v['state']=='PENDING'),None))
    try:
        await call('ideation')
        idea=await input('ideation')
        owner.store.answer(project,identity,idea['id'],{'title':'Checksum','text':'Test checksum cases'})
        await done('ideation')
        for phase in ('literature','idea_selection'):
            await call(phase); await done(phase)
        await call('proposal');proposal_result=await done('proposal')
        assert proposal_result['needs_clarification'] is ambiguous
        assert proposal_result['approval_allowed'] is not ambiguous
        assert bool(proposal_result['clarification_questions']) is ambiguous
        events=owner.store.get(project,identity)['state']['events']
        locked=[e for e in events if e['kind']=='proposal_clarification_required']
        assert bool(locked) is ambiguous
        if ambiguous:assert locked[-1]['approval_allowed'] is False
        await call('approval');first=await input('approval')
        assert first['prompt']['kind']=='proposal'
        assert first['prompt']['approval_allowed'] is not ambiguous
        if ambiguous:
            with pytest.raises(ValueError,match='schema'):
                owner.store.answer(project,identity,first['id'],{'approve':True,'reason':'Cannot bypass questions'})
        with pytest.raises(StoreConflict,match='stale'):
            await call('proposal',1)
        await asyncio.sleep(.1)
        assert len(contexts)==1 and owner.working.admissions==0

        old=first
        for round in range(2):
            pending=first if round==0 else await input('approval')
            message={'message':'Include empty and Unicode checksum cases','request_id':uuid.uuid4().hex}
            owner.store.answer(project,identity,pending['id'],message)
            owner.store.answer(project,identity,pending['id'],message)
            revised=await done('approval',round)
            assert revised['revise_proposal'] and revised['proposal_round']==round+1
            with pytest.raises(StoreConflict):
                owner.store.answer(project,identity,old['id'],{'approve':True,'reason':'Stale approval'})
            assert len(contexts)==round+1
            if round==0:
                await owner.pause(project,identity)
                await owner.start(project,identity)
                generation=owner.store.get(project,identity)['state']['generation']
                await call('ideation');await done('ideation')
                for phase in ('literature','idea_selection'):
                    await call(phase);await done(phase)
            await call('proposal',round+1);await done('proposal',round+1)
            assert len(contexts)==round+2
            assert contexts[-1][-1]['role']=='user' and contexts[-1][-1]['text']==message['message']
            await call('approval',round+1)
        ready=await input('approval')
        assert ready['prompt']['approval_allowed'] and ready['prompt']['candidate']['version']==3
        owner.store.answer(project,identity,ready['id'],{'approve':True,'reason':'Reviewed v3'})
        final=await done('approval',2)
        assert not final['revise_proposal']
        for stage in ('run_approval','execution',*RUN_PHASES,'collect'):
            await call(stage,2)
            if stage=='run_approval':
                gate=await input(stage)
                owner.store.answer(project,identity,gate['id'],{'approve':True,'reason':'Approved exact run'})
            await done(stage,2)
        assert owner.working.admissions==1
        state=owner.store.get(project,identity)['state']
        assert state['proposal_round']==0 and state['status']=='DONE'
        assert len(state['approvals'])==1 and state['approvals'][0]['version']==3
    finally:
        await owner.close()


@run_async
async def test_agent_approval_still_requires_human_clarification(repository):
    owner,project,_,spec,_=setup(repository)
    spec=spec.model_copy(deep=True)
    spec.stages['approval'].actor='agent'
    spec.stages['approval'].preset_id='default'
    spec.allow_agent_approval=True
    identity=uuid.uuid4().hex
    owner.create(project,identity,spec)
    calls=[]
    class AmbiguousPlanner(FixtureAdapter):
        def send(self,handle,message,**kwargs):
            calls.append(json.loads(message)['stage'])
            handle.stop_receipt={'tree_stopped':True,'process_exited':True}
            return SimpleNamespace(result=SimpleNamespace(summary=json.dumps({
                'needs_clarification':True,'questions':['Which inputs?'],'paraphrase':'Need scope'}),files=[]),receipt=handle.stop_receipt)
    owner.gateway._harness_catalog.resolve=lambda _:AmbiguousPlanner()
    owner.agent_turns.invoke=owner.executor.invoke
    try:
        await owner.start(project,identity)
        generation=owner.store.get(project,identity)['state']['generation']
        await owner.step(project,identity,generation,0,'ideation')
        idea=await wait_for(lambda:next((v for v in owner.store.inputs(project,identity) if v['state']=='PENDING'),None))
        owner.store.answer(project,identity,idea['id'],{'title':'Checksum','text':'Checksum tests'})
        await wait_for(lambda:owner.tasks[(identity,'0:ideation')].done())
        for phase in ('literature','idea_selection'):
            await owner.step(project,identity,generation,0,phase)
            await wait_for(lambda:owner.tasks[(identity,'0:'+phase)].done())
        await owner.step(project,identity,generation,0,'proposal')
        await wait_for(lambda:owner.tasks[(identity,'0:proposal')].done())
        await owner.step(project,identity,generation,0,'approval')
        gate=await wait_for(lambda:next((v for v in owner.store.inputs(project,identity) if v['state']=='PENDING'),None))
        assert gate['stage']=='approval' and not gate['prompt']['approval_allowed']
        with pytest.raises(ValueError):
            owner.store.answer(project,identity,gate['id'],{'approve':True,'reason':'Agent cannot bypass'})
        assert calls==['proposal'] and owner.working.admissions==0
    finally:
        await owner.close()
