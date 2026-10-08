"""M1-02: exercise full application restarts with local providers, without paid work."""
from contextlib import asynccontextmanager
import json
import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from ai_scientist.workbench.app import create_app
from ai_scientist.workbench.store import ProjectStore
from ai_scientist.workbench.working_store import WorkingStore
from test_planning import FakeRuntime, ready, request_type
from test_working import Donor, MCP


def application(tmp_path, runtime, mcp, monkeypatch, donor=None):
    @asynccontextmanager
    async def connection(config):
        yield mcp, ['kaggle_ssh_start']

    monkeypatch.setattr('ai_scientist.workbench.working.DonorSession', lambda config: donor or Donor())
    config = SimpleNamespace(workspace_root=tmp_path, shutdown_seconds=.1,
                             kaggle_username='verified-user', kaggle_account_alias='fixture-account')
    return create_app(config, bindings=SimpleNamespace(runtime=runtime, request_type=request_type),
                      mcp_connection=connection)


def wait_until(operation, condition):
    deadline = time.monotonic() + 5
    while True:
        value = operation()
        if condition(value):
            return value
        assert time.monotonic() < deadline
        threading.Event().wait(.01)


def test_discussion_answer_approval_artifacts_survive_full_restarts(tmp_path, monkeypatch):
    runtime, mcp = FakeRuntime(), MCP()
    app = application(tmp_path, runtime, mcp, monkeypatch)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Paper'}).json()['id']
        other = client.post('/api/projects', json={'name': 'Competition'}).json()['id']
        base = f'/api/projects/{project}'
        source = client.post(base + '/resources', json={'title': 'Paper source', 'content': 'Saved evidence'}).json()
        idea = client.post(base + '/ideas', json={'title': 'Restart demo', 'text': 'Implement a baseline'}).json()
        plan = {'idea_id': idea['id'], 'resource_ids': [source['id']]}
        assert client.post(base + '/plan', json=plan).status_code == 202
        proposal = wait_until(lambda: client.get(base + '/proposals').json(), bool)[0]
        assert proposal['state'] == 'NEEDS_CLARIFICATION'
    assert len(runtime.calls) == 1 and not mcp.calls

    app = application(tmp_path, runtime, mcp, monkeypatch)
    with TestClient(app) as client:
        assert len(runtime.calls) == 1
        assert client.get(base + '/proposals').json()[0] == proposal
        answer = {'proposal_id': proposal['id'], 'version': 1, 'text': 'Use a small CNN'}
        response = client.post(base + f'/ideas/{idea["id"]}/answer', json=answer)
        assert response.status_code == 200
        saved_idea = response.json()
        assert saved_idea['conversation'][-1]['text'] == answer['text']
    assert len(runtime.calls) == 1

    runtime.clarify = False
    app = application(tmp_path, runtime, mcp, monkeypatch)
    with TestClient(app) as client:
        assert client.get(base + '/ideas').json()[0] == saved_idea
        assert client.get(f'/api/projects/{other}/ideas').json() == []
        assert len(runtime.calls) == 1
        assert client.post(base + '/plan', json=plan).status_code == 202
        current = wait_until(lambda: client.get(base + '/proposals').json(), lambda items: items[0]['version'] == 2)[0]
        assert current['state'] == 'AWAITING_APPROVAL'
        submitted_context = json.loads(runtime.calls[-1].prompt.split('UNTRUSTED PROJECT CONTEXT:\n')[1])
        assert submitted_context['idea']['conversation'][-1]['text'] == answer['text']
        approval = {'version': 2, 'context_sha256': current['context_sha256']}
        run = client.post(base + f'/proposals/{current["id"]}/approve', json=approval).json()
        root = app.state.view.root(project, run['id'])
        root.mkdir(parents=True)
        artifact = json.dumps(current['context_snapshot'])
        (root / 'context.json').write_text(artifact, encoding='utf-8')
        pinned = client.get(base + '/proposals').json()[0]

    with TestClient(application(tmp_path, runtime, mcp, monkeypatch)) as client:
        assert len(runtime.calls) == 2 and not mcp.calls
        assert client.get(base + '/proposals').json()[0] == pinned
        repeated = client.post(base + f'/proposals/{current["id"]}/approve', json=approval)
        assert repeated.json()['id'] == run['id']
        assert len(client.get(base + '/history').json()['runs']) == 1
        assert client.get(f'/api/projects/{other}/history').json()['runs'] == []
        assert client.get(base + f'/runs/{run["id"]}/artifacts/context.json').text == artifact
        assert client.get(base + f'/runs/{run["id"]}').json().get('working') is None


def test_interrupted_planning_waits_for_an_explicit_request(tmp_path, monkeypatch):
    runtime, mcp = FakeRuntime(), MCP()
    runtime.clarify = False
    store = ProjectStore(tmp_path / '.workbench/projects')
    project = store.create_project('Interrupted')['id']
    source = store.save_resource(project, {'title': 'Notes', 'content': 'Evidence'})
    idea = store.save_idea(project, 'Continue from saved work', 'Interrupted proposal')
    store.reserve_plan(project, idea['id'])
    state = tmp_path / '.workbench/runtime-state.json'
    state.write_text(json.dumps({'status': 'running', 'request_id': 'old', 'role': 'mvp0_plan'}))
    base = f'/api/projects/{project}'
    with TestClient(application(tmp_path, runtime, mcp, monkeypatch)) as client:
        recovered = client.get(base + '/ideas').json()[0]
        assert recovered['state'] == 'FAILED' and 'khởi động lại' in recovered['error']
        assert client.get('/health').json()['runtime_job'] == 'interrupted'
        assert not runtime.calls and not mcp.calls
        assert client.post(base + '/plan', json={'idea_id': idea['id'], 'resource_ids': [source['id']]}).status_code == 202
        wait_until(lambda: client.get(base + '/proposals').json(), bool)
        assert len(runtime.calls) == 1 and not mcp.calls


def test_source_change_only_invalidates_dependent_pending_proposals(tmp_path, monkeypatch):
    runtime, mcp = FakeRuntime(), MCP()
    store = ProjectStore(tmp_path / '.workbench/projects')
    project = store.create_project('Source versions')['id']
    source = store.save_resource(project, {'title': 'Paper', 'content': 'Version one'})
    unrelated = store.save_resource(project, {'title': 'Unrelated notes', 'content': 'Original notes'})
    proposal_ids, idea_ids = [], []
    for title, selected in [('Pending', source), ('Approved', source), ('Unrelated', unrelated)]:
        idea = store.save_idea(project, title, title)
        idea_ids.append(idea['id'])
        context = store.context_snapshot(project, idea['id'], [selected['id']])
        proposal_ids.append(store.save_proposal(project, idea['id'], ready(selected['id']), context))
    approved = next(item for item in store.proposals(project) if item['id'] == proposal_ids[1])
    run = store.approve_proposal(project, approved['id'], 1, approved['context_sha256'])
    frozen = store.approved_snapshot(project, run['id'])
    # Merely adding another Library source must not invalidate an existing proposal.
    store.save_resource(project, {'title': 'New unselected paper', 'content': 'Extra notes'})
    assert next(item for item in store.proposals(project) if item['id'] == proposal_ids[0])['state'] == 'AWAITING_APPROVAL'
    store.save_resource(project, {'title': 'Paper', 'content': 'Version two'}, source['id'], 1)
    assert store.idea(project, idea_ids[0])['state'] == 'NEEDS_REVIEW'
    assert store.idea(project, idea_ids[1])['state'] == 'APPROVED'
    # Upgrade an old saved session that labelled a now-stale proposal as awaiting approval.
    with store.connection(project) as connection:
        connection.execute("UPDATE ideas SET state='AWAITING_APPROVAL' WHERE id=?", (idea_ids[0],))
    base = f'/api/projects/{project}'
    with TestClient(application(tmp_path, runtime, mcp, monkeypatch)) as client:
        proposals = {item['id']: item for item in client.get(base + '/proposals').json()}
        ideas = {item['id']: item for item in client.get(base + '/ideas').json()}
        assert ideas[idea_ids[0]]['state'] == 'NEEDS_REVIEW'
        assert ideas[idea_ids[2]]['state'] == 'AWAITING_APPROVAL'
        assert proposals[proposal_ids[0]]['state'] == 'STALE'
        assert proposals[proposal_ids[1]] == {**approved, 'state': 'APPROVED', 'approved_at': proposals[proposal_ids[1]]['approved_at']}
        assert proposals[proposal_ids[2]]['state'] == 'AWAITING_APPROVAL'
        rejected = client.post(base + f'/proposals/{proposal_ids[0]}/approve', json={
            'version': 1, 'context_sha256': proposals[proposal_ids[0]]['context_sha256']})
        assert rejected.status_code == 409
        assert 'cần xem lại' in rejected.json()['detail']
        assert not runtime.calls and not mcp.calls
    assert store.approved_snapshot(project, run['id']) == frozen


@pytest.mark.parametrize('phase', ['starting', 'working', 'awaiting_stop'])
def test_working_restart_only_stops_the_existing_session(tmp_path, monkeypatch, phase):
    runtime, mcp, donor = FakeRuntime(), MCP(), Donor()
    app = application(tmp_path, runtime, mcp, monkeypatch, donor)
    store = app.state.store
    project = store.create_project('Working restart')['id']
    source = store.save_resource(project, {'title': 'Notes', 'content': 'Approved evidence'})
    idea = store.save_idea(project, 'Approved work')
    context = store.context_snapshot(project, idea['id'], [source['id']])
    proposal_id = store.save_proposal(project, idea['id'], ready(source['id']), context)
    run = store.approve_proposal(project, proposal_id, 1, context['context_sha256'])['id']
    records = WorkingStore(store)
    records.reserve(project, run, 'cpu', 1800)
    root = store.directory(project) / 'runs' / run
    root.mkdir(parents=True)
    descriptor = {'notebook_ref': 'verified-user/fixture-' + run}
    records.update(project, run, state='STOPPING' if phase == 'awaiting_stop' else 'WORKING' if phase == 'working' else 'STARTING',
                   phase=phase, descriptor=descriptor if phase != 'starting' else None,
                   agent_called=int(phase != 'starting'))
    if phase == 'awaiting_stop':
        records.update(project, run, outcome='COMPLETED', summary={'succeeded': True, 'summary': 'Verified result', 'limitations': []},
                       manifest={'files': [], 'command_count': 2})
    records.append_log(project, run, 'Saved log before restart\n')
    path = f'/api/projects/{project}/runs/{run}'
    with TestClient(application(tmp_path, runtime, mcp, monkeypatch, donor)) as client:
        detail = wait_until(lambda: client.get(path).json(), lambda item: item['working']['stop_confirmed'])
        assert detail['state'] == ('COMPLETED' if phase == 'awaiting_stop' else 'FAILED')
        assert 'Kaggle dừng' in detail['report_preview']
        assert client.get(path + '/logs').json()['entries'][0]['text'] == 'Saved log before restart\n'
    calls = list(donor.calls)
    with TestClient(application(tmp_path, runtime, mcp, monkeypatch, donor)) as client:
        assert client.get(path).json()['state'] == detail['state']
        assert client.get(path + '/artifacts/report.md').status_code == 200
    assert not runtime.calls and not mcp.calls and not donor.opens
    assert donor.calls == calls and calls == [('stop', run), ('status', run)]
