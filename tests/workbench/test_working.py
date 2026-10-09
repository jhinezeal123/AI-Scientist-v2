"""Local-only Working lifecycle fixtures; no Kaggle or Codex provider calls."""
import asyncio
import base64
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import urllib.request

import pytest
from fastapi.testclient import TestClient

from ai_scientist.workbench.app import create_app
from ai_scientist.workbench.working import WorkingService, sources
from ai_scientist.workbench.store import StoreConflict
from ai_scientist.workbench.working_store import WorkingStore
from test_implementation import approved_run, setup


@pytest.fixture(autouse=True)
def workspace_cwd(tmp_path, monkeypatch):
    # Upstream Node serializes experiment paths relative to the launch directory.
    monkeypatch.chdir(tmp_path)


class Terminal:
    """Instrumented terminal used to exercise the real agent HTTP gateway."""
    def __init__(self, output):
        self.lock = threading.Lock()
        self.output = output
        self.files = {}
        self.commands = 0
        self.stop_requested = False
        self.closed = False

    def request(self, action, **body):
        if self.closed:
            raise RuntimeError('fixture disconnected')
        if action == 'exec':
            self.commands += 1
            self.output('fixture terminal output\n')
            return {'output': 'fixture terminal output\n', 'returncode': 0, 'command_count': self.commands}
        if action == 'write':
            self.files[body['path']] = base64.b64decode(body['data'])
            return {'bytes': len(self.files[body['path']])}
        if action == 'read':
            return {'data': base64.b64encode(self.files[body['path']][body.get('offset', 0):][:512_000]).decode()}
        if action == 'manifest':
            return {'command_count': self.commands, 'files': [
                {'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                for name, data in self.files.items() if name.startswith(('source/', 'output/'))]}
        if action == 'stop':
            self.stop_requested = True
            return {'stop_requested': True}
        raise AssertionError(action)

    def close(self):
        self.closed = True


class Donor:
    def __init__(self):
        self.opens = []
        self.calls = []
        self.confirm = threading.Event()
        self.confirm.set()

    def open(self, session_id, output):
        terminal = Terminal(output)
        self.opens.append((session_id, terminal))
        return terminal

    def call(self, action, session_id):
        self.calls.append((action, session_id))
        return {'session_id': session_id, 'notebook_ref': 'verified-user/fixture-' + session_id,
                'status': 'complete' if self.confirm.is_set() else 'running', 'stopped': self.confirm.is_set()}


class MCP:
    def __init__(self, pending=False, failure=False):
        self.calls = []
        self.pending, self.failure = pending, failure

    async def call_tool(self, name, body):
        self.calls.append((name, body))
        assert name == 'kaggle_ssh_start'
        if self.failure:
            raise RuntimeError('fixture MCP disconnect')
        run_id = body.get('request_id') or body['session_id']
        result = {'session_id': run_id, 'account': 'fixture-account', 'ttl_seconds': 1800,
                  'remote_directory': '/fixture/' + run_id, 'notebook_ref': 'verified-user/fixture-' + run_id,
                  'submission_status': 'CONFIRMED', 'ssh_status': 'PENDING' if self.pending and len(self.calls) == 1 else 'READY'}
        return SimpleNamespace(structuredContent=result, isError=False)


class Runtime:
    def __init__(self, fail=False, pause=False):
        self.calls = []
        self.fail, self.pause = fail, pause
        self.entered = threading.Event()

    def run(self, request, progress, cancelled):
        self.calls.append(request)
        assert request.role == 'mvp0_working'
        pinned = json.loads((request.workdir / 'working-request.json').read_text(encoding='utf-8'))
        for source in pinned['approved']['snapshot']['resources']:
            assert 'content' not in source
            assert (request.workdir / source['file_path']).is_file()
        if pinned['approved']['body'].get('split'):
            assert pinned['approved']['body']['split']['seed'] == 42
        assert 'account' not in pinned and 'token' not in pinned
        access = json.loads((request.workdir / 'terminal-access.json').read_text())
        def call(action, **body):
            req = urllib.request.Request(access['url'], json.dumps({'action': action, **body}).encode(),
                {'Authorization': 'Bearer ' + access['token'], 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.load(response)
        for source in pinned['approved']['snapshot']['resources']:
            data = base64.b64decode(call('read', path=source['file_path'])['data'])
            assert hashlib.sha256(data).hexdigest() == source['file_sha256']
        assert call('exec', command='fixture only', timeout=2)['returncode'] == 0
        call('write', path='source/workload.py', data=base64.b64encode(b'print("fixture")\n').decode())
        call('write', path='output/test.csv', data=base64.b64encode(b'id,prediction\n1,7\n').decode())
        self.entered.set()
        if self.pause:
            while not cancelled():
                threading.Event().wait(.01)
            raise RuntimeError('fixture cancelled')
        if self.fail:
            raise RuntimeError('fixture agent failed')
        return SimpleNamespace(text=json.dumps({'succeeded': True, 'summary': 'Local fixture completed',
            'limitations': ['Simulated Kaggle, no real model training'], 'output_files': ['output/test.csv']}), files={})


def fixture(tmp_path, runtime=None, mcp=None, donor=None):
    runtime, mcp, donor = runtime or Runtime(), mcp or MCP(), donor or Donor()
    store, project, run, worker, planner, implementation = setup(tmp_path, runtime)
    config = SimpleNamespace(workspace_root=tmp_path, kaggle_username='verified-user',
        kaggle_account_alias='fixture-account', working_seconds=900, kaggle_session_seconds=1800)
    service = WorkingService(planner, config, implementation.view, mcp, donor=donor, stop_seconds=.01, poll_seconds=.01)
    return store, project, run['id'], worker, planner, service, runtime, mcp, donor


async def wait_for(predicate):
    for _ in range(500):
        if predicate():
            return
        await asyncio.sleep(.01)
    raise AssertionError('fixture did not reach expected state')


def test_unstarted_approvals_do_not_block_but_remote_or_active_runs_still_do(tmp_path):
    from copy import deepcopy
    import pytest
    from ai_scientist.workbench.store import StoreConflict
    async def scenario():
        store, project, original, worker, planner, service, runtime, mcp, donor = fixture(tmp_path)
        approved = store.approved_snapshot(project, original)
        idea = store.save_idea(project, 'Another prepared idea')
        context = store.context_snapshot(project, idea['id'], [source['id'] for source in approved['snapshot']['resources']])
        proposal = store.save_proposal(project, idea['id'], approved['body'], context)
        second = await planner.approve(project, proposal, 1, context['context_sha256'])
        assert store.unstarted_run_ids(project) == {original, second['id']}
        other = store.create_project('Other prepared project')['id']
        source = store.save_resource(other, {'title':'Other source','content':'other data'})
        other_idea = store.save_idea(other, 'Prepared only')
        other_context = store.context_snapshot(other, other_idea['id'], [source['id']])
        body = deepcopy(approved['body'])
        body['data_refs'] = [source['id']]
        other_proposal = store.save_proposal(other, other_idea['id'], body, other_context)
        other_run = await planner.approve(other, other_proposal, 1, other_context['context_sha256'])
        with store.connection(other) as connection:
            connection.execute('UPDATE runs SET identity_json=? WHERE id=?', ('{"status":"running"}', other_run['id']))
        with pytest.raises(StoreConflict):
            await service.start(project, second['id'])
        with store.connection(other) as connection:
            connection.execute('UPDATE runs SET identity_json=NULL WHERE id=?', (other_run['id'],))
        assert (await service.start(project, second['id']))['state'] == 'STARTING'
        with pytest.raises(StoreConflict):
            await service.start(project, original)
        await service.tasks[project, second['id']]
        assert service.record(project, second['id'])['stop_confirmed']
        assert store.run(project, original)['state'] == 'APPROVED'
        assert store.run(other, other_run['id'])['state'] == 'APPROVED'
        await worker.close(1)
    asyncio.run(scenario())


def test_working_success_pending_resume_outputs_stop_and_unlimited_new_runs(tmp_path):
    async def check():
        store, project, run, worker, planner, service, runtime, mcp, donor = fixture(tmp_path, mcp=MCP(pending=True))
        assert (await service.start(project, run, 'NvidiaT4', 1800))['state'] == 'STARTING'
        with pytest.raises(StoreConflict):
            await service.start(project, run)
        await service.tasks[project, run]
        detail = service.detail(project, run)
        assert detail['state'] == 'COMPLETED' and detail['working']['stop_confirmed']
        assert len(runtime.calls) == len(donor.opens) == 1
        assert donor.opens[0][1].stop_requested and donor.opens[0][1].closed
        assert mcp.calls[0][1]['request_id'] == run and mcp.calls[0][1]['accelerator'] == 'NvidiaT4'
        assert mcp.calls[0][1]['competition_sources'] == ['fixture-data']
        assert mcp.calls[1][1] == {'account': 'fixture-account', 'session_id': run, 'wait_seconds': 60}
        assert 'output/test.csv' in detail['artifacts'] and 'working-stop.json' in detail['artifacts']
        assert not any('terminal-access' in name for name in detail['artifacts'])
        assert not (runtime.calls[0].workdir / 'terminal-access.json').exists()
        # MVP2 leaves report unchecked; completion proof remains a technical artifact.
        assert 'report_preview' not in detail
        assert json.loads((service.view.root(project, run) / 'working-stop.json').read_text())['stopped'] is True
        assert 'fixture terminal output' in ''.join(item['text'] for item in service.records.logs(project, run)['entries'])
        for attempt in range(3):
            request_id = str(attempt).zfill(32)
            new = await service.retry(project, run, request_id)
            assert new['id'] != run and new['identity'] is None
            assert (await service.retry(project, run, request_id))['id'] == new['id']
            await service.start(project, new['id'])
            await service.tasks[project, new['id']]
            assert service.detail(project, new['id'])['state'] == 'COMPLETED'
            run = new['id']
        assert len(runtime.calls) == 4
        await service.close(1); await planner.close(); await worker.close(1)
    asyncio.run(check())


@pytest.mark.parametrize('failure', ['agent', 'mcp'])
def test_failures_stop_and_never_replay(tmp_path, failure):
    async def check():
        _, project, run, worker, planner, service, runtime, mcp, donor = fixture(
            tmp_path, runtime=Runtime(fail=failure == 'agent'), mcp=MCP(failure=failure == 'mcp'))
        await service.start(project, run)
        await service.tasks[project, run]
        assert service.detail(project, run)['state'] == 'FAILED'
        assert len(mcp.calls) == 1 and len(runtime.calls) == (failure == 'agent')
        assert service.record(project, run)['stop_confirmed']
        await service.close(1); await planner.close(); await worker.close(1)
    asyncio.run(check())


def test_stop_proof_gates_completion_retry_and_restart(tmp_path):
    async def check():
        store, project, run, worker, planner, service, runtime, mcp, donor = fixture(tmp_path)
        donor.confirm.clear()
        await service.start(project, run)
        await wait_for(lambda: service.record(project, run)['phase'] == 'awaiting_stop')
        assert store.run(project, run)['state'] == 'STOPPING'
        with pytest.raises(StoreConflict):
            await service.retry(project, run, '8' * 32)
        with pytest.raises(StoreConflict):
            await service.start(project, run)
        await service.close(1)
        donor.confirm.set()
        restored = WorkingService(planner, service.config, service.view, mcp, donor=donor, poll_seconds=.01)
        await restored.recover()
        await restored.tasks[project, run]
        assert store.run(project, run)['state'] == 'COMPLETED'
        assert len(runtime.calls) == len(mcp.calls) == len(donor.opens) == 1
        await restored.close(1); await planner.close(); await worker.close(1)
    asyncio.run(check())


def test_user_stop_cancels_agent_and_allows_a_new_run(tmp_path):
    async def check():
        store, project, run, worker, planner, service, runtime, _, _ = fixture(tmp_path, runtime=Runtime(pause=True))
        await service.start(project, run)
        await wait_for(runtime.entered.is_set)
        await service.stop(project, run)
        assert store.run(project, run)['state'] == 'STOPPING'
        await service.tasks[project, run]
        assert store.run(project, run)['state'] == 'CANCELLED'
        assert service.record(project, run)['stop_confirmed']
        assert (await service.retry(project, run, '9' * 32))['state'] == 'APPROVED'
        assert store.run(project, run)['state'] == 'CANCELLED'
        await service.close(1); await planner.close(); await worker.close(1)
    asyncio.run(check())


def test_store_rejects_unproven_or_wrong_notebook_completion(tmp_path):
    store, project, run, worker, planner, service, _, _, _ = fixture(tmp_path)
    service.records.reserve(project, run, 'cpu', 1800)
    receipt = {'session_id': run, 'notebook_ref': 'verified-user/fixture-' + run, 'stopped': False}
    with pytest.raises(StoreConflict):
        service.records.finish(project, run, receipt, 'COMPLETED', 'report.md')
    with pytest.raises(ValueError):
        service.records.update(project, run, state='COMPLETED')
    receipt['stopped'] = True
    with pytest.raises(StoreConflict):
        service.records.finish(project, run, receipt, 'COMPLETED', 'report.md')
    service.records.update(project, run, descriptor={'notebook_ref': receipt['notebook_ref']},
        summary={'succeeded': True}, manifest={'files': []})
    with pytest.raises(StoreConflict):
        service.records.finish(project, run, {**receipt, 'notebook_ref': 'wrong/notebook'}, 'COMPLETED', 'report.md')
    asyncio.run(worker.close(1))


def test_working_http_routes_ownership_and_artifact_allowlist(tmp_path, monkeypatch):
    runtime, mcp, donor = Runtime(), MCP(), Donor()
    @asynccontextmanager
    async def connection(config):
        yield mcp, ['kaggle_ssh_start']
    monkeypatch.setattr('ai_scientist.workbench.working.DonorSession', lambda config: donor)
    config = SimpleNamespace(workspace_root=tmp_path, shutdown_seconds=1,
        kaggle_username='verified-user', kaggle_account_alias='fixture-account')
    app = create_app(config, bindings=SimpleNamespace(runtime=runtime, request_type=__import__('test_planning').request_type), mcp_connection=connection)
    project, run = approved_run(app.state.store)
    other = app.state.store.create_project('Other')['id']
    path = f'/api/projects/{project}/runs/{run["id"]}'
    with TestClient(app) as client:
        assert client.post(f'/api/projects/{other}/runs/{run["id"]}/working', json={}).status_code == 404
        assert client.post(path + '/working', json={'accelerator': 'invalid'}).status_code == 422
        assert client.post(path + '/working', json={}).status_code == 202
        assert client.post(path + '/working', json={}).status_code == 409
        for _ in range(200):
            detail = client.get(path).json()
            if detail['state'] == 'COMPLETED':
                break
            threading.Event().wait(.01)
        assert detail['state'] == 'COMPLETED'
        assert client.post(path + '/submit').status_code == 410
        assert client.post(path + '/implement').status_code == 410
        assert client.get(path + '/artifacts/output/test.csv').text == 'id,prediction\n1,7\n'
        assert client.get(path + '/artifacts/working-agent/terminal-access.json').status_code == 404
        assert client.get(path + '/logs').json()['terminal']
        assert client.post(path + '/stop').status_code == 202
