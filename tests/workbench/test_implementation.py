import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import nbformat
import pytest
from fastapi.testclient import TestClient
from ai_scientist.workbench.app import create_app
from ai_scientist.workbench.bundle import build_bundle, check_source
from ai_scientist.workbench.implementation import ImplementationService
from ai_scientist.workbench.journal import restore_journal
from ai_scientist.workbench.models import CodePayload
from ai_scientist.workbench.notebook_runner import execute_workload
from ai_scientist.workbench.service import PlanningService
from ai_scientist.workbench.store import ProjectStore, StoreConflict
from ai_scientist.workbench.worker import RuntimeWorker
from test_planning import ready, request_type


SOURCE = '''def run(context, emit):
    emit(1, {context['metric']['name']: 1.0}, total_steps=1)
    return {'measurements': {context['metric']['name']: 1.0},
            'split': {'train_sample_ids': ['a'], 'validation_sample_ids': ['b'],
                      'train_images': 1, 'validation_images': 1}, 'artifacts': []}
'''


def payload(source=SOURCE):
    return CodePayload(source=source, config={'seed':42, 'max_epochs':1, 'training_seconds':600,
                       'output_bytes':10000000, 'parameters':{}}, implementation_summary='fixture only', checks_explained=['emit'])


def approved_run(store):
    project = store.create_project('Implementation fixture')['id']
    source = store.save_resource(project, {'kind':'dataset','title':'fixture only','url':'https://www.kaggle.com/competitions/fixture-data/data', 'content':'contract fixture, no real training'})
    idea = store.save_idea(project,'fixture')
    snapshot = store.context_snapshot(project,idea['id'],[source['id']])
    proposal_id = store.save_proposal(project,idea['id'],ready(source['id']),snapshot)
    run = store.approve_proposal(project,proposal_id,1,snapshot['context_sha256'])
    return project,run


class Runtime:
    def __init__(self, bad_first=False, all_bad=False):
        self.calls=[]
        self.bad_first, self.all_bad = bad_first,all_bad
    def run(self, request, progress, cancelled):
        self.calls.append(request)
        assert request.role == 'mvp0_code'
        item = payload('def nope():\n    pass\n' if self.all_bad or self.bad_first and len(self.calls)==1 else SOURCE)
        return SimpleNamespace(text=item.model_dump_json(), files={}, session_id='fixture-session')


def setup(tmp_path, runtime):
    store=ProjectStore(tmp_path/'.workbench/projects')
    project,run=approved_run(store)
    worker=RuntimeWorker(runtime,tmp_path/'state.json')
    planner=PlanningService(store,SimpleNamespace(request_type=request_type),worker,tmp_path)
    service=ImplementationService(planner,SimpleNamespace(workspace_root=tmp_path,kaggle_username='verified-user'))
    return store,project,run,worker,planner,service


def test_gate_bundle_and_no_source_execution(tmp_path):
    runtime=Runtime()
    store,project,run,worker,planner,service=setup(tmp_path,runtime)
    approved=store.approved_context(project,run['id'])
    resource=store.resources(project)[0]
    # Live source changes after approval must not affect the coder's pinned context.
    store.save_resource(project,{'kind':'dataset','title':'changed','url':resource['url'],'content':'UNAPPROVED CHANGE'},resource['id'],1)
    async def check():
        with pytest.raises(KeyError):
            await service.start(project,'0'*32)
        assert not runtime.calls
        await service.start(project,run['id'])
        with pytest.raises(StoreConflict):
            await service.start(project,run['id'])
        await planner.task
        detail=service.detail(project,run['id'])
        assert detail['ready'] and detail['state']=='PREFLIGHT'
        assert len(runtime.calls)==1 and 'UNAPPROVED CHANGE' not in runtime.calls[0].prompt
        assert approved['context_sha256'] in runtime.calls[0].prompt
        root=service.root(project,run['id'])
        notebook=nbformat.read(root/'notebook.ipynb',as_version=4)
        nbformat.validate(notebook)
        metadata=json.loads((root/'kernel-metadata.json').read_text())
        assert metadata['competition_sources']==['fixture-data']
        assert metadata['id']=='verified-user/ailab-'+run['id']
        assert metadata['is_private'] is True and metadata['enable_internet'] is False
        assert metadata['code_file']=='notebook.ipynb'
        context=json.loads((root/'context.json').read_text())
        assert context['input_mounts']==['/kaggle/input/competitions/fixture-data']
        assert 'runtime_contract' in runtime.calls[0].prompt
        assert '/kaggle/input/competitions/fixture-data' in runtime.calls[0].prompt
        assert not list(root.rglob('result.json')) and not list(root.rglob('metrics.json'))
        manifest=json.loads((root/'bundle-manifest.json').read_text())
        assert 'source/workload.py' in manifest
        assert manifest['source/workload.py']==detail['code_sha256']
        node=json.loads((root/'journal.json').read_text())['nodes'][0]
        assert store.run(project,run['id'])['node_id']==node['id']
        await service.start(project,run['id'])
        await planner.task
        assert len(runtime.calls) == 2
        assert service.detail(project,run['id'])['ready']
        await planner.close(); await worker.close(1)
    asyncio.run(check())


def test_user_requested_repair_has_no_automatic_retry_or_total_quota(tmp_path):
    for name, all_bad in [('repair',False),('fail',True)]:
        runtime=Runtime(bad_first=True,all_bad=all_bad)
        store,project,run,worker,planner,service=setup(tmp_path/name,runtime)
        async def check():
            await service.start(project,run['id']); await planner.task
            assert len(runtime.calls) == 1
            assert service.detail(project,run['id'])['state'] == 'FAILED'
            await service.start(project,run['id']); await planner.task
            detail=service.detail(project,run['id'])
            assert len(runtime.calls)==2 and len(detail['attempts'])==2
            assert detail['ready'] is not all_bad
            assert detail['state']==('FAILED' if all_bad else 'PREFLIGHT')
            journal=restore_journal(json.loads((service.root(project,run['id'])/'journal.json').read_text()))
            assert journal.nodes[1].parent is journal.nodes[0]
            assert 'USER-REQUESTED REVISION WITHIN THE SAME APPROVED SCOPE' in runtime.calls[1].prompt
            await service.start(project,run['id']); await planner.task
            assert len(runtime.calls) == 3
            assert len(service.detail(project,run['id'])['attempts']) == 3
            await planner.close();await worker.close(1)
        asyncio.run(check())


def test_preflight_bad_config_syntax_entry_and_metadata(tmp_path):
    runtime=Runtime()
    store,project,run,worker,planner,service=setup(tmp_path,runtime)
    approved=store.approved_context(project,run['id'])
    item=payload(); item.config['seed']=99
    checks=build_bundle(tmp_path/'bad-seed',store.run(project,run['id']),approved,item,'verified-user')
    assert not checks['pass'] and 'Config seed differs' in ' '.join(checks['errors'])
    item.config['seed']=42; item.config['training_seconds']=601
    assert not build_bundle(tmp_path/'bad-limit',store.run(project,run['id']),approved,item,'verified-user')['pass']
    assert check_source('def run(context, emit): invalid !')
    assert check_source('import requests\n'+SOURCE)
    assert check_source('open("local-marker", "w").write("executed")\n'+SOURCE)
    assert not (tmp_path/'local-marker').exists()
    assert not build_bundle(tmp_path/'no-owner',store.run(project,run['id']),approved,payload(),None)['pass']
    approved['body']['expected_outputs'].append('A small model checkpoint')
    checks=build_bundle(tmp_path/'no-checkpoint',store.run(project,run['id']),approved,payload(),'verified-user')
    assert not checks['pass'] and 'checkpoint' in ' '.join(checks['errors'])
    asyncio.run(worker.close(1))


def test_restart_keeps_coder_attempt_consumed_and_no_replay(tmp_path):
    runtime=Runtime()
    store,project,run,worker,planner,service=setup(tmp_path,runtime)
    store.reserve_implementation(project,run['id'],'interrupted-request')
    reloaded=ProjectStore(tmp_path/'.workbench/projects'); reloaded.recover_implementation()
    record=reloaded.run(project,run['id'])
    assert record['state']=='FAILED' and record['attempts'][0]['state']=='FAILED'
    assert not runtime.calls
    assert reloaded.reserve_implementation(project,run['id'],'last-request')==2
    reloaded.recover_implementation()
    assert not runtime.calls
    assert reloaded.reserve_implementation(project,run['id'],'third-request') == 3
    assert reloaded.run(project,run['id'])['attempts'][0]['state'] == 'FAILED'
    asyncio.run(worker.close(1))


def test_retired_http_execution_preserves_ownership_and_saved_artifacts(tmp_path):
    store=ProjectStore(tmp_path/'.workbench/projects');project,run=approved_run(store)
    other=store.create_project('other')['id']; runtime=Runtime()
    class MCP:
        def call_tool(self,*args,**kwargs):
            raise AssertionError('T05 must never submit/train or call MCP')
    @asynccontextmanager
    async def mcp(config):
        yield MCP()
    app=create_app(SimpleNamespace(workspace_root=tmp_path,shutdown_seconds=1,kaggle_username='verified-user'),
                   bindings=SimpleNamespace(runtime=runtime,request_type=request_type),kaggle_connection=mcp)
    root=store.directory(project)/'runs'/run['id']
    root.mkdir(parents=True)
    (root/'notebook.ipynb').write_text('{"cells": []}',encoding='utf-8')
    with TestClient(app) as client:
        assert client.post(f'/api/projects/{other}/runs/{run["id"]}/implement').status_code==404
        response=client.post(f'/api/projects/{project}/runs/{run["id"]}/implement')
        assert response.status_code==410
        assert client.post(f'/api/projects/{project}/runs/{run["id"]}/implement').status_code==410
        assert client.post(f'/api/projects/{project}/runs/{run["id"]}/submit').status_code==410
        detail=client.get(f'/api/projects/{project}/runs/{run["id"]}').json()
        assert detail['state']=='APPROVED' and len(runtime.calls)==0
        assert not any(hasattr(app.state,name) for name in ('implementation','submission','monitor','results'))
        assert client.get('/health').status_code==200
        assert client.get(f'/api/projects/{project}/runs/{run["id"]}/artifacts/notebook.ipynb').status_code==200
        assert client.get(f'/api/projects/{other}/runs/{run["id"]}/artifacts/notebook.ipynb').status_code==404
        assert client.get(f'/api/projects/{project}/runs/{run["id"]}/artifacts/secret.txt').status_code==404


def test_fixed_runner_contract_finite_telemetry_and_failure(tmp_path):
    # Execute only a tiny contract fixture, never Codex source or real training locally.
    import hashlib
    context={'output_dir':str(tmp_path/'output'),'code_sha256':hashlib.sha256(SOURCE.encode()).hexdigest(),
             'run_id':'fixture','proposal_id':'fixture','proposal_version':1,'context_sha256':'fixture',
             'config':{'max_epochs':1,'training_seconds':5,'seed':42},'metric':{'name':'EMD'},
             'budget':{'output_bytes':1000000},'competition_slug':'fixture-data','data_refs':[],
             'input_mounts':[],'split':{'method':'contract fixture'}}
    execute_workload(context,SOURCE)
    result=json.loads((tmp_path/'output/result.json').read_text())
    assert result['measurements']['EMD']==1.0 and result['schema_version']==1
    assert json.loads((tmp_path/'output/metrics.json').read_text())[0]['epoch']==1
    assert 'AILAB_COMPLETE fixture' in (tmp_path/'output/runner.log').read_text()
    invalid=SOURCE.replace('1.0',"float('nan')")
    context['output_dir']=str(tmp_path/'failure');context['code_sha256']=hashlib.sha256(invalid.encode()).hexdigest()
    with pytest.raises(ValueError,match='finite'):
        execute_workload(context,invalid)
    assert not (tmp_path/'failure/result.json').exists()


def test_busy_job_rejects_planner_and_keeps_health_responsive(tmp_path):
    started,release=Event(),Event()
    class Paused(Runtime):
        def run(self,request,progress,cancelled):
            started.set();assert release.wait(3)
            return super().run(request,progress,cancelled)
    runtime=Paused()
    store,project,run,worker,planner,service=setup(tmp_path,runtime)
    async def check():
        await service.start(project,run['id'])
        assert await asyncio.to_thread(started.wait,2)
        with pytest.raises(StoreConflict):
            await planner.start(project,'invalid',[])
        assert worker.state['status']=='running'
        release.set();await planner.task
        assert service.detail(project,run['id'])['ready']
        await planner.close();await worker.close(1)
    asyncio.run(check())


def test_windows_long_prompt_preserves_full_request_in_one_allowed_file(tmp_path, monkeypatch):
    import os
    if os.name != 'nt':
        pytest.skip('Windows argv fallback')
    from ai_scientist.workbench import implementation
    monkeypatch.setattr(implementation.subprocess,'list2cmdline',lambda args:'X'*29001)
    runtime=Runtime()
    store,project,run,worker,planner,service=setup(tmp_path,runtime)
    async def check():
        await service.start(project,run['id']);await planner.task
        assert service.detail(project,run['id'])['ready']
        request=runtime.calls[0]
        assert 'Read exactly coding-request.txt' in request.prompt
        original=(request.workdir/'coding-request.txt').read_text(encoding='utf-8')
        assert 'UNTRUSTED APPROVED CONTEXT:' in original and 'fixture only' in original
        assert store.implementation_snapshot(project,run['id'])['context_sha256'] in original
        await planner.close();await worker.close(1)
    asyncio.run(check())


def test_old_failed_run_cannot_resume_while_another_run_is_active(tmp_path):
    runtime=Runtime()
    store,project,run,worker,planner,service=setup(tmp_path,runtime)
    store.reserve_implementation(project,run['id'],'first')
    store.recover_implementation()
    approved_run(store)
    async def check():
        with pytest.raises(StoreConflict,match='đang chặn tạo code'):
            await service.start(project,run['id'])
        assert not runtime.calls and len(store.run(project,run['id'])['attempts'])==1
        await planner.close();await worker.close(1)
    asyncio.run(check())


def test_saved_source_review_blocks_submission_without_an_extra_coder_call(tmp_path):
    runtime=Runtime()
    store,project,run,worker,planner,service=setup(tmp_path,runtime)
    async def check():
        await service.start(project,run['id']);await planner.task
        record=store.run(project,run['id']);node=record['attempts'][0]['node']
        checks={**record['attempts'][0]['checks'],'pass':False,'errors':['Missing approved checkpoint']}
        with pytest.raises(StoreConflict):
            store.record_preflight_review(project,run['id'],{**checks,'code_sha256':'0'*64},node)
        store.record_preflight_review(project,run['id'],checks,node)
        detail=service.detail(project,run['id'])
        assert detail['state']=='FAILED' and not detail['ready']
        assert len(runtime.calls)==1 and len(detail['attempts'])==1
        assert 'Missing approved checkpoint' in detail['error']
        await planner.close();await worker.close(1)
    asyncio.run(check())
