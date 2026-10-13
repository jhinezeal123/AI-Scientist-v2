"""Run defaults are authoritative while workflow grants remain immutable."""
import asyncio
import json
from types import SimpleNamespace
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from ai_scientist.workbench.api import library_router
from ai_scientist.workbench.n8n_api import create_n8n_router
from ai_scientist.workbench.project_configuration import ProjectConfiguration
from ai_scientist.workbench.run_configuration import RunConfiguration
from ai_scientist.workbench.store import StoreConflict
from tests.workbench.test_n8n_workflows import setup,repository


def test_run_defaults_migrate_and_workflow_cannot_overwrite_them(repository):
    owner,project,flow,spec,_=setup(repository)
    settings=owner.controls.configuration
    before=owner.store.get(project,flow)['spec']
    # Simulate the old combined representation from existing project data.
    with owner.projects.connection(project) as con:
        con.execute('UPDATE project_configuration SET body_json=?',(json.dumps({'resource_ids':[],'workflow':before}),))
    saved=settings.get(project)
    assert saved['run']==RunConfiguration.from_workflow(before).model_dump(mode='json')
    run=RunConfiguration.model_validate({**saved['run'],'account':'new-account','accelerator':'NvidiaT4',
                                       'ttl_seconds':600,'execution_seconds':240,'output_bytes':1234})
    new=settings.save_run(project,saved['version'],run)
    assert owner.store.get(project,flow)['spec']==before
    stale=spec.model_copy(update={'account':'stale-account','execution_seconds':60})
    merged=settings.workflow_spec(project,stale,new['version'])
    assert merged.account=='new-account' and merged.execution_seconds==240 and merged.output_bytes==1234
    settings.update(project,workflow=stale.model_dump(mode='json'))
    assert settings.get(project)['run']==run.model_dump(mode='json')
    with owner.projects.connection(project) as con:
        stored=json.loads(con.execute('SELECT body_json FROM project_configuration').fetchone()[0])
    assert not set(RunConfiguration.model_fields)&set(stored['workflow'])
    assert ProjectConfiguration(owner.projects).get(project)['run']==new['run']
    with pytest.raises(StoreConflict):
        settings.save_run(project,saved['version'],run)
    asyncio.run(owner.close())


def test_run_api_save_then_workflow_uses_saved_settings_and_retries_frozen_grant(repository,monkeypatch):
    monkeypatch.setenv('AI_SCIENTIST_AGENT_CONTROL_TOKEN','fixture-only-key')
    owner,project,_,spec,_=setup(repository)
    accounts=SimpleNamespace(require=lambda account:None)
    owner.working.accounts=accounts
    app=FastAPI()
    app.state.runtime=SimpleNamespace(runtime=owner.gateway)
    app.state.store=owner.projects
    app.state.working=owner.working
    app.state.research_workflows=owner
    app.include_router(library_router(owner.projects,repository))
    app.include_router(create_n8n_router())
    prefix=f'/api/projects/{project}/configuration'
    with TestClient(app,headers={'Authorization':'Bearer fixture-only-key'}) as client:
        saved=client.get(prefix).json()
        run={**saved['run'],'account':'chosen-account','ttl_seconds':600,'execution_seconds':240}
        response=client.put(prefix+'/run',json={'version':saved['version'],'run':run})
        assert response.status_code==200,response.text
        changed=response.json()
        path=f'/api/agent-management/projects/{project}/workflows'
        identity=uuid.uuid4().hex
        payload={'request_id':identity,'configuration_version':saved['version'],'spec':spec.model_dump(mode='json')}
        assert client.post(path,json=payload).status_code==409
        assert not any(r['id']==identity for r in owner.list(project))
        payload['configuration_version']=changed['version']
        response=client.post(path,json=payload)
        assert response.status_code==200,response.text
        grant=response.json()['spec']
        assert grant['account']=='chosen-account' and grant['execution_seconds']==240
        version=client.get(prefix).json()['version']
        assert client.put(prefix+'/run',json={'version':version,'run':{**run,'account':'later-account'}}).status_code==200
        retry=client.post(path,json=payload)
        assert retry.status_code==200 and retry.json()['spec']==grant
        payload['spec']['max_runs']=2
        assert client.post(path,json=payload).status_code==409
        invalid={**run,'execution_seconds':599}
        assert client.put(prefix+'/run',json={'version':version,'run':invalid}).status_code==422
    assert owner.working.admissions==0 and not owner.client.requests
    asyncio.run(owner.close())
