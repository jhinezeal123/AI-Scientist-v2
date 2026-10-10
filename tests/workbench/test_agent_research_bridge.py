import asyncio
import copy
import importlib
import json
from types import SimpleNamespace

import pytest

from ai_scientist.workbench.store import ProjectStore
from ai_scientist.workbench.team_context import stage_team_context
from tests.workbench.test_agent_team_execution import repository,FixtureRegistry,Platform,AgentStore,models,wait_finished

P=Platform.__module__.rsplit('.',1)[0]
bridge_module=importlib.import_module(P+'.research_bridge')
bundles=importlib.import_module(P+'.bundles')
interfaces=importlib.import_module(P+'.interfaces')


class Working:
    def __init__(self,projects,root):
        self.projects=projects
        self.view=SimpleNamespace(root=lambda project,run:root/'.workbench/runs'/project/run)
        self.records={}
        self.calls=0
        self.fail_after_reserve=False
    def record(self,project,run):
        return self.records.get((project,run))
    async def start(self,project,run,**kwargs):
        self.calls+=1
        self.records[(project,run)]={'phase':'STARTING'}
        if self.fail_after_reserve:
            raise ConnectionError('Simulated lost reply')
        return {'run_id':run,'state':'STARTING'}


@pytest.fixture
def setup(repository):
    projects=ProjectStore(repository/'.workbench/projects',repository)
    project=projects.create_project('Bridge test')['id']
    source=projects.save_resource(project,{'title':'Library source','content':'Fixed test cases'})
    idea=projects.save_idea(project,'Improve inference',mode='etc',desired_output='Return a short execution report')
    context=projects.context_snapshot(project,idea['id'],[source['id']])
    body={'needs_clarification':False,'paraphrase':'Measure fixed cases','objective':'Measure fixed cases','implementation_steps':['Measure and report'],
        'budget':{'execution_seconds':600}}
    proposal=projects.save_proposal(project,idea['id'],body,context)
    run=projects.approve_proposal(project,proposal,1,context['context_sha256'])
    fixture=repository/'fixture.py'
    fixture.write_text('''import sys,json
request=json.load(sys.stdin); role=json.loads(request['prompt'].split('\\n',1)[1])['role']
print(json.dumps({'summary':role,'files':[{'path':'src/demo.py','content':'reviewed code\\n'}] if role=='builder' else [],'checks':[],'handoff':role}))
''')
    control=Platform(AgentStore(repository/'.workbench/control.sqlite'),repository,registry=FixtureRegistry(fixture))
    control.context.projects=projects
    spec={**models.templates()[1],'project_id':project}
    control.create('bridge',models.RigSpec.model_validate(spec))
    previous=None
    for role in ('lead','builder','qa','reviewer'):
        task=control.enqueue('bridge',role,role,models.TaskRequest(instruction='Improve within the approved scope'),depends_on=previous)
        previous=task['id']
    control.start('bridge')
    team=wait_finished(control,'bridge',4)
    control.pause('bridge')
    assert all(t['state']=='DONE' for t in team['tasks']),team
    working=Working(projects,repository)
    bridge=bridge_module.ResearchBridge(control,projects,working)
    review=next(t for t in team['tasks'] if t['seat']=='reviewer')
    command=bridge_module.ResearchCommand(**bridge.binding('bridge',run['id']),request_id='research-request',
        review_task_id=review['id'],checkpoint=review['result']['checkpoint'],ttl_seconds=600)
    yield control,bridge,command,working,source
    control.close()


def test_approved_bridge_duplicate_remote_replay_and_staged_context(setup,tmp_path):
    control,bridge,command,working,_=setup
    first=asyncio.run(bridge.dispatch('bridge',command))
    second=asyncio.run(bridge.dispatch('bridge',command))
    assert first==second and working.calls==1
    root=working.view.root(command.project_id,command.run_id)
    workdir=tmp_path/'stage';workdir.mkdir()
    approved=bridge.projects.approved_snapshot(command.project_id,command.run_id)
    staged=stage_team_context(root,workdir,approved)
    assert staged['request_id']==command.request_id
    assert (workdir/'team-source/src/demo.py').read_text()=='reviewed code\n'
    assert bridge.commands('bridge')[0]['run']['id']==command.run_id


@pytest.mark.parametrize('field,value',[('proposal_version',2),('context_sha256','f'*64),('scope_sha256','f'*64),('budget',{}),('ttl_seconds',1000),('checkpoint','f'*40)])
def test_approval_binding_and_review_scope_fail_closed(setup,field,value):
    _,bridge,command,working,_=setup
    changed=command.model_copy(update={field:value})
    with pytest.raises(ValueError):
        asyncio.run(bridge.dispatch('bridge',changed))
    assert working.calls==0


def test_lost_dispatch_reply_reconciles_existing_working_intent_without_replay(setup):
    control,bridge,command,working,_=setup
    working.fail_after_reserve=True
    with pytest.raises(ConnectionError):
        asyncio.run(bridge.dispatch('bridge',command))
    with pytest.raises(ValueError,match='UNKNOWN'):
        asyncio.run(bridge.dispatch('bridge',command))
    receipt=asyncio.run(bridge.reconcile('bridge',command.request_id,retry=True))
    assert receipt['reconciled_existing_intent'] and working.calls==1
    assert asyncio.run(bridge.dispatch('bridge',command))==receipt


def test_bundle_integrity_and_library_scoping(setup):
    control,bridge,command,working,source=setup
    rig=control.store.rig('bridge')
    ref=control.context.library_reference(rig,'library',source['id'],['builder'])
    spec=rig.model_copy(update={'context':[ref]})
    control.store.update_spec('bridge',spec,1)
    assert control.context.pack(spec,'builder')[0]['kind']=='library'
    assert control.context.pack(spec,'reviewer')==[]
    # Fixture registry does not install native harnesses; bundle needs an explicit
    # local matching configuration, with no installation or executable import.
    control.store.put_harness(models.HarnessSpec(id='codex',kind='native_codex'))
    package=bundles.export_bundle(control,'bridge')
    assert 'managed_home' not in json.dumps(package) and 'executable' not in json.dumps(package)
    changed=copy.deepcopy(package);changed['payload']['spec']['name']='Tampered'
    with pytest.raises(ValueError,match='checksum'):
        bundles.import_bundle(control,'bad',changed)
    imported=bundles.import_bundle(control,'imported',package)
    assert imported['enabled']==0
    bridge.projects.save_resource(command.project_id,{'title':'Library source','content':'Changed cases'},resource_id=source['id'],expected_version=1)
    with pytest.raises(ValueError,match='version changed'):
        control.context.pack(spec,'builder')


def test_mcp_negotiation_tool_schema_and_scoped_http_client():
    import io
    client=SimpleNamespace(call=lambda path,method='GET',body=None:[])
    mcp=interfaces.Mcp(client)
    with pytest.raises(ValueError,match='Initialize'):
        mcp.handle({'method':'tools/list'})
    assert mcp.handle({'method':'initialize'})['protocolVersion']=='2025-11-25'
    mcp.handle({'method':'notifications/initialized'})
    assert mcp.handle({'method':'tools/list'})['tools'][0]['inputSchema']['type']=='object'
    source=io.StringIO(json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'team_control','arguments':{'path':'/teams'}}})+'\n')
    output=io.StringIO();mcp.stdio(source,output)
    assert json.loads(output.getvalue())['result']['structuredContent']['result']==[]
    with pytest.raises(ValueError,match='HTTPS'):
        interfaces.Client('http://evil.example',token='fixture')
