"""Project cleanup uses disposable local folders and never opens Kaggle sessions."""
import asyncio
from types import SimpleNamespace
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from ai_scientist.workbench.api import library_router
from ai_scientist.workbench.named_paths import filesystem_path
from ai_scientist.workbench.store import ProjectStore, StoreConflict
from ai_scientist.workbench.working_store import SCHEMA


def run_record(store, project, state='COMPLETED', stopped=None, hidden=False):
    idea = store.save_idea(project, 'Disposable idea')
    proposal = store.save_proposal(project, idea['id'], {'objective': 'fixture'}, store.context_snapshot(project, idea['id'], []))
    run = uuid.uuid4().hex
    with store.connection(project) as connection:
        connection.execute('INSERT INTO runs(id,proposal_id,state,intent_key,artifact_dir,deleted_at) VALUES(?,?,?,?,?,?)',
                           (run, proposal, state, run, 'runs/'+run, 'hidden' if hidden else None))
        if stopped is not None:
            connection.execute(SCHEMA)
            connection.execute('INSERT INTO working_runs(run_id,session_id,phase,accelerator,ttl_seconds,started_at,stop_confirmed) VALUES(?,?,?,?,?,?,?)',
                               (run, run, 'stopped' if stopped else 'stopping', 'cpu', 60, 'now', int(stopped)))
    return run


def test_api_purges_whole_project_keeps_neighbors_and_last_project_can_be_deleted(tmp_path):
    store = ProjectStore(tmp_path/'projects')
    deleted, keep = store.create_project('Xóa project'), store.create_project('Giữ project')
    root = store.directory(deleted['id'])
    store.import_file(deleted['id'], 'Paper', 'paper.txt', b'FULL_FILE_CONTENT')
    run_record(store, deleted['id'], stopped=True, hidden=True)
    for part in ('planning/job/context.json', 'runs/fixture/report.md', 'experiment/fixture/logs/0-run/tree.html'):
        target = root/part
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('DISPOSABLE_ARTIFACT')
    # Exercise the long Windows paths used by project-packaged experiments.
    deep = filesystem_path(root)/'experiment'/('experiment_'+'x'*110)/('node_'+'x'*80)/'output.csv'
    deep.parent.mkdir(parents=True)
    deep.write_bytes(b'values\n1\n')
    outside = tmp_path/'experiments'/'upstream'
    outside.mkdir(parents=True)
    (outside/'keep.txt').write_text('UPSTREAM')
    app = FastAPI()
    app.include_router(library_router(store, tmp_path))
    with TestClient(app) as client:
        url = '/api/projects/'+deleted['id']
        assert client.request('DELETE', url, json={'name':'Wrong name'}).status_code == 409
        assert root.exists()
        result = client.request('DELETE', url, json={'name':deleted['name']})
        assert result.status_code == 200 and result.json()['freed_bytes'] > 0
        assert result.json()['removed_files'] >= 7 and not root.exists()
        assert client.get(url+'/resources').status_code == 404
        assert client.request('DELETE', url, json={'name':deleted['name']}).status_code == 404
        assert client.get('/api/projects').json() == [keep]
        assert ProjectStore(store.root).list_projects() == [keep]
        assert (outside/'keep.txt').read_text() == 'UPSTREAM'
        assert client.request('DELETE', '/api/projects/'+keep['id'], json={'name':keep['name']}).status_code == 200
        assert client.get('/api/projects').json() == []
        assert not list(store.root.iterdir())


@pytest.mark.parametrize('state,stopped,hidden', [
    ('WORKING',False,False), ('UNKNOWN',None,True), ('FAILED',False,False),
    ('SUBMITTING',None,False), ('COLLECTING',None,False), ('IMPLEMENTING',None,False),
])
def test_active_or_unresolved_runs_block_even_when_hidden(tmp_path, state, stopped, hidden):
    store = ProjectStore(tmp_path/'projects')
    project = store.create_project('Blocked')
    run_record(store, project['id'], state, stopped, hidden)
    with pytest.raises(StoreConflict, match='Kaggle'):
        store.delete_project(project['id'], project['name'])
    assert store.directory(project['id']).is_dir()


def test_planning_and_wrong_identity_block_before_removing_files(tmp_path):
    store = ProjectStore(tmp_path/'projects')
    project = store.create_project('Planning')
    idea = store.save_idea(project['id'], 'Question')
    store.reserve_plan(project['id'], idea['id'])
    with pytest.raises(StoreConflict, match='proposal'):
        store.delete_project(project['id'], project['name'])
    for identity in ('../escape', 'f'*32):
        with pytest.raises(KeyError):
            store.delete_project(identity, project['name'])
    assert store.ideas(project['id'])[0]['state'] == 'PLANNING'


def test_busy_agent_and_finishing_working_task_block_api(tmp_path):
    store = ProjectStore(tmp_path/'projects')
    project = store.create_project('Busy')
    app = FastAPI()
    app.include_router(library_router(store, tmp_path))
    future = SimpleNamespace(done=lambda:False)
    app.state.service = SimpleNamespace(lock=asyncio.Lock(), worker=SimpleNamespace(future=future,state={'status':'running'}),task=None)
    with TestClient(app) as client:
        url = '/api/projects/'+project['id']
        assert client.request('DELETE', url, json={'name':project['name']}).status_code == 409
        app.state.service.worker.future = None
        app.state.service.worker.state['status'] = 'completed'
        app.state.working = SimpleNamespace(tasks={(project['id'],'run'):future})
        assert client.request('DELETE', url, json={'name':project['name']}).status_code == 409
        app.state.working.tasks.clear()
        assert client.request('DELETE', url, json={'name':project['name']}).status_code == 200


def test_linked_descendant_refused_without_removing_any_file(tmp_path):
    import os
    store = ProjectStore(tmp_path/'projects')
    project = store.create_project('Linked')
    root = store.directory(project['id'])
    outside = tmp_path/'outside'
    outside.mkdir()
    (outside/'keep.txt').write_text('KEEP')
    link = root/'linked'
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError as exc:
        if os.name != 'nt':
            raise
        # Junctions need no Windows symlink privilege.
        import subprocess
        subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)], check=True, capture_output=True)
    try:
        with pytest.raises(ValueError, match='liên kết'):
            store.delete_project(project['id'], project['name'])
        assert (root/'project.sqlite').is_file() and (outside/'keep.txt').read_text() == 'KEEP'
    finally:
        if link.is_symlink():
            link.unlink()
        else:
            link.rmdir()


def test_locked_artifact_returns_retryable_conflict_and_keeps_database(tmp_path, monkeypatch):
    import ai_scientist.workbench.project_deletion as deletion
    store = ProjectStore(tmp_path/'projects')
    project = store.create_project('Locked')
    root = store.directory(project['id'])
    (root/'library'/'locked.txt').write_text('KEEP_UNTIL_UNLOCKED')
    original = deletion.shutil.rmtree
    def locked(path):
        raise PermissionError('file held open')
    monkeypatch.setattr(deletion.shutil,'rmtree',locked)
    with pytest.raises(StoreConflict, match='thử xóa lại'):
        store.delete_project(project['id'], project['name'])
    assert store.project(project['id']) == project
    assert (root/'library'/'locked.txt').is_file()
    monkeypatch.setattr(deletion.shutil,'rmtree',original)
    assert store.delete_project(project['id'], project['name'])['deleted']
    assert not root.exists()
