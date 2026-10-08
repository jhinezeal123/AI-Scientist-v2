from copy import deepcopy
import hashlib
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from ai_scientist.workbench.api import library_router
from ai_scientist.workbench.named_paths import folder_title, rename_folder
from ai_scientist.workbench.run_view import RunView
from ai_scientist.workbench.store import ProjectStore, canonical, digest
from test_working import fixture


def test_project_and_source_names_match_their_folders(tmp_path):
    store = ProjectStore(tmp_path / 'projects')
    project = store.create_project('Soil Grain Size MVP0')
    assert store.directory(project['id']).name == project['name'] == 'Soil Grain Size MVP0'
    source = store.save_resource(project['id'], {'kind':'text','title':'Soil competition — rules','content':'Rules'})
    assert source['file_path'] == 'library/Soil competition — rules/v1/source.md'
    assert store.library(project['id']).path(source['file_path']).is_file()
    assert ProjectStore(store.root).project(project['id']) == project


def test_collisions_and_windows_characters_are_reflected_in_gui_names(tmp_path):
    store = ProjectStore(tmp_path)
    first = store.create_project('QA: đọc / ghi')
    second = store.create_project('QA: đọc / ghi')
    assert first['name'] == 'QA_ đọc _ ghi'
    assert second['name'] == first['name'] + ' (2)'
    assert store.directory(second['id']).name == second['name']
    a = store.save_resource(first['id'], {'kind':'text','title':'Bài tập: CNN?','content':'first'})
    b = store.save_resource(first['id'], {'kind':'text','title':'Bài tập: CNN?','content':'second'})
    assert a['title'] == 'Bài tập_ CNN_' and b['title'] == a['title'] + ' (2)'
    assert store.library(first['id']).path(a['file_path']).read_bytes() != store.library(first['id']).path(b['file_path']).read_bytes()
    for title in ('CON', 'nul.txt', 'LPT1'):
        assert folder_title(title).startswith('_')
    with pytest.raises(ValueError):
        store.create_project('...')
    with pytest.raises(ValueError):
        store.library(first['id']).path('library/../v1/source.md')


def test_source_rename_preserves_pinned_versions_and_reserves_old_names(tmp_path):
    store = ProjectStore(tmp_path / 'projects')
    project = store.create_project('Thử tên')['id']
    source = store.save_resource(project, {'kind':'text','title':'Tên cũ','content':'pinned original'})
    idea = store.save_idea(project, 'Read original')
    context = store.context_snapshot(project, idea['id'], [source['id']])
    frozen = deepcopy(context)
    old_bytes = store.library(project).path(source['file_path']).read_bytes()
    updated = store.save_resource(project, {'kind':'text','title':'Tên mới','content':'updated'}, source['id'], 1)
    assert updated['title'] == 'Tên mới' and updated['file_path'] == 'library/Tên mới/v2/source.md'
    assert not (store.directory(project) / 'library/Tên cũ').exists()
    assert store.library(project).path(source['file_path']).read_bytes() == old_bytes
    agent = store.library(project).agent_snapshot(context['snapshot'])
    assert agent['resources'][0]['file_path'] == 'library/Tên mới/v1/source.md'
    assert agent['resources'][0]['file_sha256'] == hashlib.sha256(old_bytes).hexdigest()
    store.library(project).stage(context['snapshot'], tmp_path / 'agent')
    assert (tmp_path / 'agent/library/Tên mới/v1/source.md').read_bytes() == old_bytes
    assert context == frozen
    replacement = store.save_resource(project, {'kind':'text','title':'Tên cũ','content':'different source'})
    assert replacement['title'] == 'Tên cũ (2)'
    restarted = ProjectStore(store.root)
    assert restarted.library(project).agent_snapshot(context['snapshot']) == agent


def test_legacy_id_folders_migrate_without_changing_approved_snapshots(tmp_path):
    store, project, run_id, _, _, working, *_ = fixture(tmp_path)
    approved = store.approved_snapshot(project, run_id)
    proposal_id = store.run(project, run_id)['proposal_id']
    source = approved['snapshot']['resources'][0]
    # Reproduce the old path-only snapshot while retaining exact approved bytes/hash.
    with store.connection(project) as connection:
        snapshot = deepcopy(approved['snapshot'])
        snapshot['resources'][0]['file_path'] = f"library/{source['id']}/v1/source.md"
        connection.execute('UPDATE proposals SET context_snapshot_json=?,context_sha256=? WHERE id=?',
                           (canonical(snapshot), digest(canonical(snapshot)), proposal_id))
    frozen = store.approved_snapshot(project, run_id)
    root = working.view.root(project, run_id)
    root.mkdir(parents=True)
    (root / 'report.md').write_text('preserved report')
    folder = store.library(project).source_path(source['id'], 1).parent.parent
    (folder / '.resource.json').unlink()
    folder.rename(folder.with_name(source['id']))
    named = store.directory(project)
    named.rename(store.root / project)
    restarted = ProjectStore(store.root)
    assert not (store.root / project).exists()
    assert restarted.directory(project).name == restarted.project(project)['name']
    assert restarted.approved_snapshot(project, run_id) == frozen
    ref = restarted.library(project).agent_snapshot(frozen['snapshot'])['resources'][0]
    assert ref['file_path'] == f"library/{source['title']}/v1/source.md"
    assert restarted.library(project).path(ref['file_path']).is_file()
    view = RunView(restarted, tmp_path, lambda:False)
    assert (view.root(project, run_id) / 'report.md').read_text() == 'preserved report'


def test_source_api_reads_old_version_by_id_after_title_change(tmp_path):
    store = ProjectStore(tmp_path / 'projects')
    project = store.create_project('API files')['id']
    source = store.save_resource(project, {'kind':'text','title':'Before','content':'Original'})
    store.save_resource(project, {'kind':'text','title':'After','content':'Updated'}, source['id'], 1)
    app = FastAPI()
    app.include_router(library_router(store, tmp_path))
    with TestClient(app) as client:
        response = client.get(f"/api/projects/{project}/library/{source['id']}/versions/1")
        assert response.status_code == 200 and 'Original' in response.text and 'Updated' not in response.text
        assert client.get('/api/projects').json()[0]['library_path'] == str(store.directory(project) / 'library')


def test_old_source_folder_cannot_be_impersonated_by_reference(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project('Safe')['id']
    a = store.save_resource(project, {'kind':'text','title':'One','content':'secret A'})
    b = store.save_resource(project, {'kind':'text','title':'Two','content':'secret B'})
    fake = {key:value for key,value in a.items() if key != 'content'}
    fake.update(file_path=b['file_path'], file_sha256=b['file_sha256'])
    with pytest.raises(ValueError, match='resource/version'):
        store.library(project).reference(fake)


@pytest.mark.skipif(os.name != 'nt', reason='Windows Explorer coordination')
def test_windows_directory_lock_uses_shell_rename_without_losing_files(tmp_path, monkeypatch):
    source = tmp_path / 'Source'
    source.mkdir()
    (source / 'proof.txt').write_text('preserve this file')
    destination = tmp_path / 'Destination'
    def denied(*args):
        raise PermissionError('Simulated Explorer directory handle')
    monkeypatch.setattr(Path, 'rename', denied)
    rename_folder(source, destination)
    assert not source.exists() and (destination / 'proof.txt').read_text() == 'preserve this file'
    with pytest.raises(ValueError):
        rename_folder(destination, tmp_path / 'elsewhere/escape')
