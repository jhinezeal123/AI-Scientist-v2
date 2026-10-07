import hashlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_scientist.workbench.api import library_router
from ai_scientist.workbench.store import ProjectStore, StoreConflict
from ai_scientist.workbench.working_store import WorkingStore
from test_working import fixture


def test_versioned_files_and_staged_copies_preserve_approved_content(tmp_path):
    store = ProjectStore(tmp_path / 'projects')
    project = store.create_project('Files')['id']
    assert (store.root / project / 'library').is_dir()
    source = store.save_resource(project, {'kind':'text','title':'Rules','content':'UNIQUE_SOURCE_V1'})
    idea = store.save_idea(project, 'Read rules')
    context = store.context_snapshot(project, idea['id'], [source['id']])
    ref = context['snapshot']['resources'][0]
    assert 'content' not in ref and 'UNIQUE_SOURCE_V1' not in json.dumps(context)
    data = store.library(project).path(ref['file_path']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == ref['file_sha256']
    store.save_resource(project, {'kind':'text','title':'Rules','content':'UNIQUE_SOURCE_V2'}, source['id'], 1)
    workspace = tmp_path / 'agent'
    store.library(project).stage(context['snapshot'], workspace)
    assert (workspace / ref['file_path']).read_bytes() == data
    assert 'UNIQUE_SOURCE_V2' not in (workspace / ref['file_path']).read_text()
    restarted = ProjectStore(store.root)
    assert restarted.library(project).path(ref['file_path']).read_bytes() == data
    with pytest.raises(ValueError):
        store.library(project).path('../another-project/source.md')
    with pytest.raises(ValueError, match='hash'):
        store.library(project).reference({**ref, 'file_sha256':'0'*64})
    other = store.create_project('Other')['id']
    with pytest.raises(FileNotFoundError):
        store.library(other).reference(ref)


def test_legacy_inline_snapshot_can_stage_its_original_version(tmp_path):
    store = ProjectStore(tmp_path / 'projects')
    project = store.create_project('Old')['id']
    source = store.save_resource(project, {'kind':'text','title':'Old','content':'legacy source'})
    # A saved MVP0 approval may contain an inline source without file metadata.
    legacy = {k:v for k,v in source.items() if not k.startswith('file_')}
    stage = tmp_path / 'legacy-agent'
    snapshot = {'resources':[legacy]}
    store.library(project).stage(snapshot, stage)
    ref = store.library(project).agent_snapshot(snapshot)['resources'][0]
    assert 'content' not in ref
    assert 'legacy source' in (stage/ref['file_path']).read_text()


def test_delete_restore_keeps_runs_snapshots_and_artifacts(tmp_path):
    store, project, run_id, worker, planner, working, *_ = fixture(tmp_path)
    approved = store.approved_snapshot(project, run_id)
    idea_id = approved['snapshot']['idea']['id']
    root = working.view.root(project, run_id)
    root.mkdir(parents=True)
    artifact = root / 'report.md'
    artifact.write_text('keep this result')
    store.set_deleted(project, 'runs', run_id)
    assert store.history(project)['runs'] == []
    assert store.history(project, include_deleted=True)['runs'][0]['deleted_at']
    assert store.approved_snapshot(project, run_id) == approved and artifact.read_text() == 'keep this result'
    with pytest.raises(StoreConflict):
        WorkingStore(store).reserve(project, run_id, 'cpu', 600)
    store.set_deleted(project, 'ideas', idea_id)
    assert store.ideas(project) == []
    with pytest.raises(KeyError):
        store.context_snapshot(project, idea_id, [])
    store.set_deleted(project, 'ideas', idea_id, False)
    store.set_deleted(project, 'runs', run_id, False)
    assert store.history(project)['runs'][0]['id'] == run_id
    assert store.ideas(project)[0]['id'] == idea_id
    assert store.approved_snapshot(project, run_id) == approved


def test_delete_cannot_hide_unresolved_session_and_api_is_project_scoped(tmp_path):
    store, project, run_id, *_ = fixture(tmp_path)
    other = store.create_project('Other')['id']
    records = WorkingStore(store)
    records.reserve(project, run_id, 'cpu', 600)
    app = FastAPI()
    app.include_router(library_router(store, tmp_path))
    with TestClient(app) as client:
        path = f'/api/projects/{project}/runs/{run_id}'
        assert client.delete(path).status_code == 409
        records.update(project, run_id, state='UNKNOWN', phase='awaiting_stop')
        assert client.delete(path).status_code == 409
        assert client.delete(f'/api/projects/{other}/runs/{run_id}').status_code == 404
        records.finish(project, run_id, {'stopped':True,'session_id':run_id}, 'FAILED')
        assert client.delete(path).status_code == 200
        assert client.get(f'/api/projects/{project}/history').json()['runs'] == []
        assert client.post(path+'/restore').status_code == 200
        assert len(client.get(f'/api/projects/{project}/history').json()['runs']) == 1
        source = store.resources(project)[0]
        url = f"/api/projects/{project}/library/{source['id']}/versions/{source['version']}"
        response = client.get(url)
        assert response.status_code == 200 and source['content'] in response.text
        assert client.get(url.replace(project, other)).status_code == 404
