"""Project team storage, preset persistence and sandbox scope without model calls."""
import importlib
import json
from types import SimpleNamespace

from ai_scientist.workbench.store import ProjectStore, StoreConflict
from tests.workbench.test_agent_team_api import client, repository, Gateway, models
import pytest
from threading import Event, Thread


def bind(browser, gateway, repository):
    projects = ProjectStore(repository/'.workbench/projects', repository)
    browser.app.state.store = projects
    gateway.projects = projects
    return projects


def test_project_team_and_presets_survive_restart_and_devices_keep_scope(client, repository):
    browser, gateway = client
    projects = bind(browser, gateway, repository)
    first = projects.create_project('First project')
    second = projects.create_project('Second project')
    prefix = '/api/agent-management'
    preset = {'id':'chosen','name':'My pair','harness':'codex','model':'fixture-model'}
    assert browser.put(prefix+'/agent-presets/chosen', json=preset).status_code == 200
    assert len(browser.get(prefix+'/templates').json()) == 1
    teams = [browser.post(prefix+'/projects/'+p['id']+'/team').json() for p in (first, second)]
    control = gateway.team_platform(teams[0]['id'])
    spec = teams[0]['spec']
    spec['seats'][1].update(harness=preset['harness'], model=preset['model'])
    response = browser.put(prefix+'/teams/'+teams[0]['id'], json={'spec':spec,'revision':1})
    assert response.status_code == 200, response.text
    assert browser.post(prefix+'/projects/'+first['id']+'/team').json()['revision'] == 2
    task = control.enqueue(teams[0]['id'], 'proposal', 'unique', models.TaskRequest(instruction='Do not execute'))
    assert gateway.platform.store.rigs() == []
    assert control.store.path == projects.directory(first['id'])/'agents/agent-management.sqlite'
    other = gateway.team_platform(teams[1]['id'])
    assert other.store.snapshot(teams[1]['id'])['tasks'] == []
    credential = browser.post(prefix+'/teams/'+teams[0]['id']+'/seats/proposal/credential').json()['token']
    headers = {'Authorization':'Bearer '+credential}
    assert browser.get(prefix+'/teams/'+teams[0]['id'], headers=headers).status_code == 200
    assert browser.get(prefix+'/teams/'+teams[1]['id'], headers=headers).status_code == 403
    with pytest.raises(StoreConflict):
        projects.delete_project(first['id'], first['name'])
    control.store.cancel_pending(teams[0]['id'],task['id'])
    path, checkpoint = control.workspaces.ensure(teams[0]['id'],'proposal','HEAD')
    control.store.seat_workspace(teams[0]['id'],'proposal',path,checkpoint)
    gateway.close()
    restored = Gateway(SimpleNamespace(executable='',model=None), repository)
    restored.projects = projects
    try:
        snapshot = restored.team_platform(teams[0]['id']).store.snapshot(teams[0]['id'])
        assert snapshot['spec']['seats'][1]['model'] == 'fixture-model'
        assert snapshot['tasks'][0]['state'] == 'CANCELLED'
        Presets = importlib.import_module(Gateway.__module__.rsplit('.',1)[0]+'.presets').Presets
        assert preset in Presets(restored.control_store).list()
        projects.delete_project(first['id'], first['name'], lambda: restored.release_project(first['id']))
        assert not path.exists()
        assert str(path).replace('\\','/') not in other.workspaces.git(repository,'worktree','list','--porcelain')
        assert projects.project(second['id'])['name'] == second['name']
    finally:
        restored.close()


def test_legacy_team_migrates_tasks_messages_and_worktree(client, repository):
    browser, gateway = client
    projects = bind(browser, gateway, repository)
    project = projects.create_project('Migrated project')
    spec = models.RigSpec(name='Existing', project_id=project['id'], seats=[models.AgentSpec(id='proposal')])
    old = gateway.platform
    old.create('existing', spec)
    task = old.enqueue('existing','proposal','pending',models.TaskRequest(instruction='Preserve me'))
    old.store.queue.send('existing','proposal','*','Existing chat')
    path, checkpoint = old.workspaces.ensure('existing','proposal','HEAD')
    old.store.seat_workspace('existing','proposal',path,checkpoint)
    result = gateway.project_platform(project['id'])
    snapshot = result.store.snapshot('existing')
    assert snapshot['tasks'][0]['id'] == task['id']
    assert result.store.chatroom('existing')[0]['body'] == 'Existing chat'
    assert not path.exists()
    assert result.workspaces.path('existing','proposal').is_dir()
    assert snapshot['seats'][0]['worktree'] == str(result.workspaces.path('existing','proposal'))
    assert old.store.rigs() == []
    assert old.store.path.with_name(old.store.path.name+'.before-project-storage.bak').exists()
    assert gateway.project_platform(project['id']).store.snapshot('existing')['tasks'] == snapshot['tasks']


def test_project_sandbox_denies_neighbor_and_project_data(client, repository, monkeypatch):
    browser, gateway = client
    projects = bind(browser, gateway, repository)
    project, neighbor = projects.create_project('Owned'), projects.create_project('Neighbor')
    control = gateway.project_platform(project['id'])
    control.create('owned',models.RigSpec(name='Owned',project_id=project['id'],seats=[models.AgentSpec(id='proposal')]))
    workspace,_ = control.workspaces.ensure('owned','proposal','HEAD')
    runtime = control.workspaces.root.parent/'runtimes/fixture'
    runtime.mkdir(parents=True)
    package = Gateway.__module__.rsplit('.',1)[0]
    isolation = importlib.import_module(package+'.windows_isolation')
    monkeypatch.setattr(isolation,'refresh_scope',lambda *a,**k:None)
    terminal = importlib.import_module(package+'.terminal')
    argv = terminal.sandbox_command(__import__('sys').executable,workspace,models.PermissionPolicy(),repository,
                                    ['fixture'],provider_home=runtime)
    config = argv[3]
    assert json.dumps(str(projects.directory(neighbor['id']).resolve()))+'="deny"' in config
    assert json.dumps(str((projects.directory(project['id'])/'project.sqlite').resolve()))+'="deny"' in config
    assert json.dumps(str(workspace.resolve()))+'="read"' in config


def test_project_release_does_not_invert_catalog_and_project_locks(client, repository):
    browser, gateway = client
    projects = bind(browser,gateway,repository)
    project = projects.create_project('Concurrent cleanup')
    gateway.project_platform(project['id'])
    from ai_scientist.workbench.named_paths import PATH_LOCK
    lookup_started = Event()
    def lookup():
        with gateway._lock:
            lookup_started.set()
            projects.directory(project['id'])
    reader = Thread(target=lookup,daemon=True)
    release = Thread(target=lambda:gateway.release_project(project['id']),daemon=True)
    try:
        with PATH_LOCK:
            reader.start()
            assert lookup_started.wait(1)
            release.start()
            release.join(1)
            assert not release.is_alive(), 'Deletion must not wait on a lookup holding the catalog lock'
    finally:
        reader.join(2)
        release.join(2)
