"""Local regressions for Working without the historical training contract."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ai_scientist.workbench.app import create_app
from ai_scientist.workbench.models import PlanPayload, WorkingProposal
from ai_scientist.workbench.store import StoreConflict
from ai_scientist.workbench.ssh_terminal import collect_files
from test_planning import request_type
from test_working import Donor, Bootstrap, Runtime, Terminal, fixture


@pytest.fixture(autouse=True)
def workspace_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def proposal(**extra):
    return {'needs_clarification': False, 'paraphrase': 'Create a CSV',
            'objective': 'Create a synthetic CSV', 'implementation_steps': ['Generate and save the CSV'], **extra}


def forbidden(*args, **kwargs):
    raise AssertionError('Working must not call the legacy notebook contract')


def guard_legacy(monkeypatch):
    monkeypatch.setattr('ai_scientist.workbench.bundle.build_bundle', forbidden)
    monkeypatch.setattr('ai_scientist.workbench.bundle.check_source', forbidden)
    monkeypatch.setattr('ai_scientist.workbench.implementation.ImplementationService.__init__', forbidden)
    monkeypatch.setattr('ai_scientist.workbench.submission.SubmissionService.__init__', forbidden)
    monkeypatch.setattr('ai_scientist.workbench.monitor.RunMonitor.__init__', forbidden)
    monkeypatch.setattr('ai_scientist.workbench.collection.RunResultsService.__init__', forbidden)


@pytest.mark.parametrize('with_reference', [False, True])
def test_idea_to_working_without_training_fields_or_legacy_gates(tmp_path, monkeypatch, with_reference):
    class GenericRuntime(Runtime):
        def run(self, request, progress, cancelled):
            if request.role != 'mvp0_plan':
                return super().run(request, progress, cancelled)
            self.calls.append(request)
            context = json.loads(request.prompt.split('UNTRUSTED PROJECT CONTEXT:\n')[1])
            body = proposal(data_refs=[item['id'] for item in context['resources']])
            return SimpleNamespace(text=json.dumps(body), files={})

    runtime, donor, bootstrap = GenericRuntime(), Donor(), Bootstrap()
    donor.start = bootstrap.start
    @asynccontextmanager
    async def connection(config):
        yield donor
    guard_legacy(monkeypatch)
    monkeypatch.setattr('ai_scientist.workbench.working.DonorSession', lambda config: donor)
    config = SimpleNamespace(workspace_root=tmp_path, shutdown_seconds=1,
        kaggle_username='verified-user', kaggle_account_alias='fixture-account')
    app = create_app(config, bindings=SimpleNamespace(runtime=runtime, request_type=request_type), kaggle_connection=connection)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Generic Working'}).json()['id']
        base = '/api/projects/' + project
        idea = client.post(base + '/ideas', json={'text': 'Create a synthetic CSV', 'title': 'CSV'}).json()
        references = []
        if with_reference:
            reference = client.post(base + '/resources', json={'kind': 'dataset', 'title': 'Optional reference',
                'url': 'https://www.kaggle.com/datasets/fixture-owner/example', 'content': ''}).json()
            assert reference['status'] == 'reference_only'
            references.append(reference['id'])
        assert client.post(base + '/plan', json={'idea_id': idea['id'], 'resource_ids': references}).status_code == 202
        for _ in range(300):
            proposals = client.get(base + '/proposals').json()
            if proposals:
                break
            threading.Event().wait(.01)
        saved = proposals[0]
        assert saved['state'] == 'AWAITING_APPROVAL'
        assert not any(field in saved['body'] for field in ('split', 'metric'))
        assert saved['body']['budget'] == {} and len(runtime.calls) == 1 and bootstrap.calls == []
        approved = client.post(base + '/proposals/' + saved['id'] + '/approve', json={
            'version': saved['version'], 'context_sha256': saved['context_sha256']})
        assert approved.status_code == 200
        path = base + '/runs/' + approved.json()['id']
        assert client.post(path + '/working', json={}).status_code == 202
        for _ in range(300):
            detail = client.get(path).json()
            if detail['state'] == 'COMPLETED':
                break
            threading.Event().wait(.01)
        assert detail['state'] == 'COMPLETED' and detail['working']['stop_confirmed']
        assert detail['attempts'] == [] and 'collection' not in detail
        assert client.get(path + '/artifacts/output/test.csv').text == 'id,prediction\n1,7\n'
        assert bootstrap.calls[0][1]['dataset_sources'] == (['fixture-owner/example'] if with_reference else [])
        assert bootstrap.calls[0][1]['competition_sources'] == []
        assert [call.role for call in runtime.calls] == ['mvp0_plan', 'mvp0_working']
        assert client.post(path + '/implement').status_code == client.post(path + '/submit').status_code == 410


def test_optional_training_details_and_user_constraints_have_no_legacy_caps():
    body = proposal(split='Task-specific split', metric={'name': 'Any metric'},
                    budget={'training_seconds': 3600, 'output_bytes': 100_000_000, 'epochs': 10})
    assert WorkingProposal.model_validate(body).budget['output_bytes'] == 100_000_000
    assert PlanPayload.model_validate(proposal()).implementation_steps
    for value in (0, -1, True, '600'):
        with pytest.raises(ValueError):
            WorkingProposal.model_validate(proposal(budget={'output_bytes': value}))


def test_active_roles_do_not_select_old_agent_platform_contracts():
    from ai_scientist.workbench.agents.outputs import research_output_schema
    assert research_output_schema('mvp0_plan') is None
    assert research_output_schema('mvp0_working') is None


@pytest.mark.parametrize('limit', [None, 20_000_000])
def test_collect_general_artifact_above_old_10mb_cap(tmp_path, limit):
    terminal = Terminal(lambda text: None)
    data = b'x' * 10_000_001
    terminal.files = {'output/arbitrary.bin': data}
    manifest = collect_files(terminal, tmp_path, limit)
    assert manifest['files'][0]['sha256'] == hashlib.sha256(data).hexdigest()
    assert (tmp_path / 'output/arbitrary.bin').read_bytes() == data
    with pytest.raises(ValueError, match='budget'):
        collect_files(terminal, tmp_path, 100)


def test_failed_legacy_run_retries_into_working_without_rebuilding_bundle(tmp_path, monkeypatch):
    async def check():
        store, project, old, worker, planner, service, runtime, _, _ = fixture(tmp_path)
        with store.connection(project) as connection:
            connection.execute("UPDATE runs SET state='FAILED',error='Legacy preflight failed' WHERE id=?", (old,))
        root = service.view.root(project, old)
        (root / 'source').mkdir(parents=True)
        (root / 'source/workload.py').write_text('print("no run or emit signature")', encoding='utf-8')
        guard_legacy(monkeypatch)
        new = await service.retry(project, old, 'b' * 32)
        assert new['state'] == 'APPROVED' and new['attempts'] == []
        assert json.loads((service.view.root(project, new['id']) / 'retry-feedback.json').read_text())['previous_sources']
        await service.start(project, new['id'])
        await service.tasks[project, new['id']]
        assert service.detail(project, new['id'])['state'] == 'COMPLETED'
        assert store.run(project, old)['state'] == 'FAILED' and len(runtime.calls) == 1
        await service.close(1)
        await planner.close()
        await worker.close(1)
    asyncio.run(check())


def test_legacy_reconcile_only_reads_pinned_status(tmp_path, monkeypatch):
    async def check():
        store, project, old, worker, planner, service, runtime, bootstrap, donor = fixture(tmp_path)
        identity = {'kernel_ref': 'verified-user/old-notebook', 'username': 'verified-user', 'version': 1}
        with store.connection(project) as connection:
            connection.execute("UPDATE runs SET state='UNKNOWN',identity_json=? WHERE id=?", (json.dumps(identity), old))
        receipts = []
        def inspect(kernel_ref):
            receipts.append(kernel_ref)
            return {'notebook_ref': kernel_ref, 'status': 'complete', 'stopped': True}
        donor.inspect = inspect
        guard_legacy(monkeypatch)
        updated = await service.reconcile(project, old)
        assert updated['state'] == 'REMOTE_SUCCEEDED' and updated['identity'] == {**identity, 'status': 'complete'}
        assert receipts == [identity['kernel_ref']] and runtime.calls == bootstrap.calls == []
        donor.inspect = lambda kernel_ref: {'notebook_ref': 'wrong/notebook', 'status': 'complete', 'stopped': True}
        with pytest.raises(StoreConflict):
            await service.reconcile(project, old)
        assert store.run(project, old)['state'] == 'REMOTE_SUCCEEDED'
        await service.close(1)
        await planner.close()
        await worker.close(1)
    asyncio.run(check())


@pytest.mark.parametrize('case', ['idle', 'running', 'wrong_owner', 'wrong_account', 'bad_count', 'unavailable'])
def test_unknown_unreadable_notebook_requires_verified_account_idle(tmp_path, case):
    async def check():
        store, project, old, worker, planner, service, runtime, _, donor = fixture(tmp_path)
        identity = {'kernel_ref': 'verified-user/old-notebook', 'username': 'verified-user'}
        with store.connection(project) as connection:
            connection.execute("UPDATE runs SET state='UNKNOWN',identity_json=? WHERE id=?", (json.dumps(identity), old))
        donor.inspect = lambda ref: (_ for _ in ()).throw(RuntimeError('fixture inaccessible notebook'))
        calls = []
        def account_idle():
            calls.append('idle')
            if case == 'unavailable':
                raise RuntimeError('fixture unavailable')
            receipt = {'account': 'fixture-account', 'username': 'verified-user',
                       'active_session_count': 0, 'idle': True, 'observed_at': '2026-10-07T08:44:52Z'}
            if case == 'running': receipt.update(active_session_count=1, idle=False)
            if case == 'wrong_owner': receipt['username'] = 'other-user'
            if case == 'wrong_account': receipt['account'] = 'other-account'
            if case == 'bad_count': receipt['active_session_count'] = False
            return receipt
        donor.account_idle = account_idle
        if case == 'idle':
            proof = await service.check_idle()
            assert proof['idle'] and proof['unresolved_notebooks'] == [identity['kernel_ref']]
            assert proof['account_observation']['active_session_count'] == 0
        else:
            with pytest.raises(StoreConflict):
                await service.check_idle()
        assert len(calls) == 1 and store.run(project, old)['state'] == 'UNKNOWN' and runtime.calls == []
        await service.close(1)
        await planner.close()
        await worker.close(1)
    asyncio.run(check())
