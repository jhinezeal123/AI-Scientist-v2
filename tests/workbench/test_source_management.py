"""Library cards' backing behavior, using temporary files and no remote sessions."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from ai_scientist.workbench.api import library_router
from ai_scientist.workbench.resources import source_urls
from ai_scientist.workbench.source_deletion import checked_directory, remove_source_files
from ai_scientist.workbench.store import ProjectStore, StoreConflict
from ai_scientist.workbench.working import sources
from test_ingestion import paper_plan, pdf_bytes
from test_working import fixture


def project_source(tmp_path):
    store = ProjectStore(tmp_path/'projects')
    project = store.create_project('Library')['id']
    source = store.import_file(project, 'Paper', 'paper.pdf', pdf_bytes(['PAGE_ONE', 'PAGE_TWO']))
    idea = store.save_idea(project, 'Read this paper')
    context = store.context_snapshot(project, idea['id'], [source['id']])
    return store, project, source, idea, context


def test_description_urls_are_references_and_mounts_remain_selected(tmp_path):
    store = ProjectStore(tmp_path/'projects')
    project = store.create_project('URLs')['id']
    app = FastAPI()
    app.include_router(library_router(store, tmp_path))
    base = f'/api/projects/{project}'
    competition = 'https://www.kaggle.com/competitions/example/data'
    dataset = 'https://www.kaggle.com/datasets/owner/images'
    with TestClient(app) as client:
        response = client.post(base+'/resources', json={'title':'Kaggle links', 'content':f'{competition}\n{dataset}'})
        assert response.status_code == 201
        source = response.json()
        assert source['url'] == competition and source['urls'] == [competition, dataset]
        assert source['status'] == 'reference_only'
        other = store.save_resource(project, {'title':'Unselected', 'content':'https://kaggle.com/datasets/other/private'})
        idea = store.save_idea(project, 'Use selected links')
        context = store.context_snapshot(project, idea['id'], [source['id'], other['id']])
        assert all('content' not in ref for ref in context['snapshot']['resources'])
        assert sources({'body':{'data_refs':[source['id']]}, 'snapshot':context['snapshot']}) == (['example'], ['owner/images'])
        source = client.put(base+f"/resources/{source['id']}", json={'title':'Notes', 'content':f'PRIVATE_DESCRIPTION\n{dataset}', 'expected_version':1}).json()
        assert source['status'] == 'provided_text' and source['urls'] == [dataset]
        assert 'PRIVATE_DESCRIPTION' not in json.dumps(store.context_snapshot(project, idea['id'], [source['id']]))
        assert ProjectStore(store.root).resources(project)[0] == source
        legacy = client.post(base+'/resources', json={'kind':'dataset','title':'Legacy API','url':dataset,'content':''}).json()
        assert legacy['kind'] == 'dataset' and legacy['status'] == 'reference_only'


def test_url_parsing_handles_punctuation_duplicates_and_credentials():
    assert source_urls({'content':'See (https://example.org/a_(b)).\nhttps://example.org/a_(b)\n'
                        '<https://kaggle.com/datasets/user/data>, https://secret:token@example.org/x https://[broken'}) == [
        'https://example.org/a_(b)', 'https://kaggle.com/datasets/user/data']
    assert source_urls({'urls':None}) == []


def test_delete_removes_all_versions_and_agent_copies_without_retained_files(tmp_path):
    store, project, source, idea, context = project_source(tmp_path)
    proposal = store.save_proposal(project, idea['id'], paper_plan(source['id']), context)
    run = store.approve_proposal(project, proposal, 1, context['context_sha256'])
    approved = deepcopy(store.approved_snapshot(project, run['id']))
    root = store.directory(project)
    planning = root/'planning'/uuid.uuid4().hex
    working = root/'runs'/run['id']/'working-agent'
    for workdir in (planning, working):
        store.library(project).stage(context['snapshot'], workdir)
    store.import_file(project, 'Renamed paper', 'new.pdf', pdf_bytes(['VERSION_TWO']), source['id'], 1)
    updated_context = store.context_snapshot(project, idea['id'], [source['id']])
    store.library(project).stage(updated_context['snapshot'], working)
    keep = store.import_file(project, 'Keep', 'keep.txt', b'UNRELATED_SOURCE')
    report = working.parent/'report.md'
    report.write_text('Historical result')
    originals = [path for path in root.rglob('*') if path.is_file() and 'library' in path.parts and keep['title'] not in path.parts]
    expected_bytes = sum(path.stat().st_size for path in originals)
    result = store.delete_resource(project, source['id'])
    assert result['removed_files'] == len(originals) and result['freed_bytes'] == expected_bytes > 0
    assert all(not path.exists() for path in originals)
    assert not (root/'library'/'Renamed paper').exists()
    assert not (planning/'library'/'Paper').exists()
    assert not (working/'library'/'Paper').exists() and not (working/'library'/'Renamed paper').exists()
    assert not list(root.rglob('*trash*')) and not list(root.rglob('*archive*'))
    assert store.resources(project) == [keep]
    assert store.approved_snapshot(project, run['id']) == approved
    assert report.read_text() == 'Historical result'
    with store.connection(project) as connection:
        assert connection.execute('SELECT count(*) FROM source_ingestions WHERE resource_id=?', (source['id'],)).fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM source_deletions').fetchone()[0] == 0
    with pytest.raises(FileNotFoundError, match='đã bị xóa'):
        store.library(project).stage(context['snapshot'], tmp_path/'agent')
    legacy = {'resources':[source]}
    with pytest.raises(FileNotFoundError, match='đã bị xóa'):
        store.library(project).agent_snapshot(legacy)
    restarted = ProjectStore(store.root)
    assert restarted.resources(project) == [keep] and not (root/'library'/'Paper').exists()


def test_delete_stales_pending_proposal_and_invalidates_context(tmp_path):
    store, project, source, idea, context = project_source(tmp_path)
    proposal = store.save_proposal(project, idea['id'], paper_plan(source['id']), context)
    store.delete_resource(project, source['id'])
    assert store.proposals(project)[0]['state'] == 'STALE'
    with pytest.raises(StoreConflict):
        store.approve_proposal(project, proposal, 1, context['context_sha256'])
    with pytest.raises(KeyError):
        store.context_snapshot(project, idea['id'], [source['id']])


@pytest.mark.parametrize('state', ['STARTING', 'WORKING', 'STOPPING', 'IMPLEMENTING', 'SUBMITTING'])
def test_delete_refuses_a_source_used_by_active_run(tmp_path, state):
    store, project, source, idea, context = project_source(tmp_path)
    proposal = store.save_proposal(project, idea['id'], paper_plan(source['id']), context)
    run = store.approve_proposal(project, proposal, 1, context['context_sha256'])
    with store.connection(project) as connection:
        connection.execute('UPDATE runs SET state=? WHERE id=?', (state, run['id']))
    with pytest.raises(StoreConflict, match='run sử dụng'):
        store.delete_resource(project, source['id'])
    assert store.resources(project) == [source]
    unused = store.save_resource(project, {'title':'Unused', 'content':'free to delete'})
    assert store.delete_resource(project, unused['id'])['deleted']


def test_delete_refuses_during_planning_and_runtime_worker(tmp_path):
    store, project, source, idea, _ = project_source(tmp_path)
    with store.connection(project) as connection:
        connection.execute("UPDATE ideas SET state='PLANNING' WHERE id=?", (idea['id'],))
    with pytest.raises(StoreConflict, match='proposal'):
        store.delete_resource(project, source['id'])
    app = FastAPI()
    app.include_router(library_router(store, tmp_path))
    app.state.service = SimpleNamespace(lock=asyncio.Lock(), worker=SimpleNamespace(future=SimpleNamespace(done=lambda:False)))
    with TestClient(app) as client:
        response = client.delete(f"/api/projects/{project}/resources/{source['id']}")
        assert response.status_code == 409 and 'agent' in response.json()['detail']


@pytest.mark.parametrize('recover', ['retry', 'restart'])
def test_partial_delete_retries_without_recreating_source_files(tmp_path, monkeypatch, recover):
    store, project, source, idea, context = project_source(tmp_path)
    workdir = store.directory(project)/'planning'/uuid.uuid4().hex
    store.library(project).stage(context['snapshot'], workdir)
    import ai_scientist.workbench.source_deletion as deletion
    original_remove = deletion.shutil.rmtree
    calls = []
    def fail_after_copy(path):
        calls.append(path)
        if len(calls) == 2:
            raise PermissionError('file is open')
        original_remove(path)
    monkeypatch.setattr(deletion.shutil, 'rmtree', fail_after_copy)
    with pytest.raises(StoreConflict, match='Chưa xóa hết'):
        store.delete_resource(project, source['id'])
    assert not (workdir/context['snapshot']['resources'][0]['file_path']).exists()
    pending = store.resources(project)[0]
    assert pending['deletion_pending'] and 'attachment' not in pending
    with pytest.raises(KeyError):
        store.context_snapshot(project, idea['id'], [source['id']])
    with pytest.raises(StoreConflict):
        store.import_file(project, 'Paper', 'paper.pdf', pdf_bytes(['new']), source['id'], 1)
    monkeypatch.setattr(deletion.shutil, 'rmtree', original_remove)
    if recover == 'restart':
        store = ProjectStore(store.root)
    else:
        store.delete_resource(project, source['id'])
    assert store.resources(project) == []
    assert not (store.directory(project)/'library'/'Paper').exists()
    with store.connection(project) as connection:
        assert connection.execute('SELECT count(*) FROM source_deletions').fetchone()[0] == 0


def test_permanent_delete_api_is_project_scoped_and_files_become_unavailable(tmp_path):
    store, project, source, _, _ = project_source(tmp_path)
    other = store.create_project('Other')['id']
    app = FastAPI()
    app.include_router(library_router(store, tmp_path))
    base = f'/api/projects/{project}'
    with TestClient(app) as client:
        assert client.delete(f"/api/projects/{other}/resources/{source['id']}").status_code == 404
        response = client.delete(base+f"/resources/{source['id']}")
        assert response.status_code == 200 and response.json()['freed_bytes'] > 0
        for suffix in ['', '/original', '/pages/1']:
            assert client.get(base+f"/library/{source['id']}/versions/1"+suffix).status_code == 404
        assert client.delete(base+f"/resources/{source['id']}").status_code == 404
        assert client.get(base+'/resources').json() == []


def test_deletion_paths_refuse_outside_and_other_source_ownership(tmp_path):
    store, project, source, _, _ = project_source(tmp_path)
    library = store.library(project)
    for path in ['../outside', 'library/..', 'library', 'runs/abc/working-agent/library/Paper']:
        with pytest.raises(ValueError):
            checked_directory(store.directory(project), path)
    keep = store.save_resource(project, {'title':'Keep', 'content':'KEEP_BYTES'})
    with pytest.raises(ValueError, match='another resource'):
        remove_source_files(library, source['id'], {'paths':['library/Keep']})
    assert store.resources(project) == [source, keep]


def test_deleted_source_cannot_open_paid_working_session(tmp_path):
    async def check():
        store, project, run_id, worker, planner, service, runtime, mcp, donor = fixture(tmp_path)
        source = store.resources(project)[0]
        store.delete_resource(project, source['id'])
        with pytest.raises(FileNotFoundError, match='đã bị xóa'):
            await service.start(project, run_id)
        assert donor.opens == [] and runtime.calls == []
        await service.close(1)
        await planner.close()
        await worker.close(1)
    asyncio.run(check())
