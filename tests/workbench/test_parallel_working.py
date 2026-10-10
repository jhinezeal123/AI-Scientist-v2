"""Parallel runs through real workers and HTTP terminal bridges; local providers."""
import asyncio
import json
import threading
from types import SimpleNamespace
import pytest

from ai_scientist.workbench.accounts import AccountCatalog
from ai_scientist.workbench.working import WorkingService
from test_implementation import approved_run
from test_working import Bootstrap, Donor, Runtime, fixture, wait_for, cookie_fixture


@pytest.fixture(autouse=True)
def workspace_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


async def add_run(store, project, parent, planner, research=None):
    approved = store.approved_snapshot(project, parent)
    idea = store.save_idea(project, 'Parallel fixture')
    context = store.context_snapshot(project, idea['id'], [row['id'] for row in approved['snapshot']['resources']])
    body = {**approved['body'], **({'research':research} if research is not None else {})}
    proposal = store.save_proposal(project, idea['id'], body, context)
    return (await planner.approve(project, proposal, 1, context['context_sha256']))['id']


class Provider:
    """Visible provider sessions, independent terminals and optional API lag."""
    def __init__(self, service, tmp_path, *, visible=True, hold=None):
        self.donor, self.bootstrap = Donor(), Bootstrap()
        self.visible, self.hold = visible, hold
        self.active = {'a.txt': {}, 'b.txt': {}}
        self.external = {'a.txt': [], 'b.txt': []}
        self.lock = threading.Lock()
        self.probes = []
        profiles = tmp_path/'bundle'/'profiles'
        entries = {}
        for alias in ('a', 'b'):
            (profiles/alias).mkdir(parents=True)
            (profiles/alias/'token.txt').write_text('KGAT_fixture_only')
            entries[alias+'.txt'] = {'alias':alias, 'username':'verified-user',
                                    'token_file':f'profiles/{alias}/token.txt'}
        (profiles/'accounts.json').write_text(json.dumps({'accounts':entries}))
        service.config.kaggle_account_alias = 'a.txt'
        service.accounts = AccountCatalog(profiles.parent, 'a.txt')
        service.donor = self.for_account('a.txt')

    def for_account(self, account):
        def observe():
            with self.lock:
                refs = list(self.external[account])
                if self.visible:
                    refs.extend(self.active[account].values())
                self.probes.append(account)
            return {'account':account, 'username':'verified-user', 'observed_at':'now',
                    'readiness':'busy' if refs else 'verified_idle', 'idle':not refs,
                    'active_session_count':len(refs), 'active_sessions':[{'ref':ref} for ref in refs]}
        def start(body):
            result = {**self.bootstrap.start(body), 'account':account}
            if self.hold:
                assert self.hold.wait(5)
            with self.lock:
                self.active[account][result['session_id']] = result['notebook_ref']
                assert len(self.active[account]) + len(self.external[account]) <= 2
            return result
        def control(action, run_id):
            receipt = self.donor.call(action, run_id)
            if receipt['stopped']:
                with self.lock:
                    self.active[account].pop(run_id, None)
            return receipt
        return SimpleNamespace(start=start, open=self.donor.open, call=control,
                               account_readiness=observe, for_account=self.for_account)


def batch_item(run, account='a.txt'):
    return {'run_id':run, 'account':account, 'accelerator':'cpu', 'ttl_seconds':1800}


async def cleanup(service, planner, worker):
    await service.close(1)
    await planner.close()
    await worker.close(1)


def test_batch_workers_and_terminals_overlap_and_stop_is_independent(tmp_path):
    async def scenario():
        items = fixture(tmp_path, runtime=Runtime(pause=True))
        store, project, first, worker, planner, service, runtime, *_ = items
        provider = Provider(service, tmp_path)
        second = await add_run(store, project, first, planner)
        third = await add_run(store, project, first, planner)
        try:
            result = await service.start_batch(project, [batch_item(run) for run in (first, second, third)])
            assert [row['state'] for row in result['runs']] == ['STARTING', 'STARTING', 'QUEUED']
            await wait_for(lambda: len(runtime.calls) == 2 and all(
                service.record(project, run)['phase'] == 'working' for run in (first, second))
                and len(provider.donor.opens) == 2 and all(terminal.commands for _, terminal in provider.donor.opens))
            for run in (first, second):
                assert not service.workers[project, run].future.done()
                assert len(service.records.logs(project, run)['entries']) >= 3
            assert service.workers[project, first] is not service.workers[project, second]
            assert not worker.future  # Planning does not own the Working jobs.
            assert len(provider.donor.opens) == 2
            assert provider.donor.opens[0][1] is not provider.donor.opens[1][1]
            access = [json.loads((service.view.root(project, run)/'working-agent'/'terminal-access.json').read_text())
                      for run in (first, second)]
            assert access[0]['url'] != access[1]['url'] and access[0]['token'] != access[1]['token']
            await service.stop(project, first)
            await service.tasks[project, first]
            assert not service.workers[project, second].cancelled.is_set()
            assert not service.workers[project, second].future.done()
            await wait_for(lambda: len(runtime.calls) == 3)
            assert sum(body.get('request_id') == third for _, body in provider.bootstrap.calls) == 1
        finally:
            await cleanup(service, planner, worker)
    asyncio.run(scenario())


def test_reservations_gate_simultaneous_requests_before_provider_visibility(tmp_path):
    async def scenario():
        release = threading.Event()
        store, project, first, worker, planner, service, runtime, *_ = fixture(tmp_path, runtime=Runtime(pause=True))
        provider = Provider(service, tmp_path, visible=False, hold=release)
        second = await add_run(store, project, first, planner)
        third = await add_run(store, project, first, planner)
        try:
            results = await asyncio.gather(*(service.start(project, run, account='a.txt') for run in (first, second, third)))
            assert [row['state'] for row in results].count('STARTING') == 2
            assert [row['state'] for row in results].count('QUEUED') == 1
            await wait_for(lambda: len(provider.bootstrap.calls) == 2)
            assert not runtime.calls  # Both provider requests are still in flight.
            assert service._account_occupancy('a.txt', {'active_session_count':0}) == 2
            release.set()
            await wait_for(lambda: len(runtime.calls) == 2)
            assert store.run(project, third)['state'] == 'QUEUED'
        finally:
            release.set()
            await cleanup(service, planner, worker)
    asyncio.run(scenario())


def test_full_account_does_not_block_other_account_and_queue_drains_in_parallel(tmp_path):
    async def scenario():
        store, project, first, worker, planner, service, runtime, *_ = fixture(tmp_path, runtime=Runtime(pause=True))
        provider = Provider(service, tmp_path)
        provider.external['a.txt'] = ['verified-user/external-1', 'verified-user/external-2']
        runs = [first] + [await add_run(store, project, first, planner) for _ in range(3)]
        try:
            result = await service.start_batch(project, [batch_item(run, 'a.txt' if i < 2 else 'b.txt') for i, run in enumerate(runs)])
            assert [row['state'] for row in result['runs']] == ['QUEUED', 'QUEUED', 'STARTING', 'STARTING']
            await wait_for(lambda: len(runtime.calls) == 2)
            assert all(body['account'] == 'b.txt' for _, body in provider.bootstrap.calls)
            with provider.lock:
                provider.external['a.txt'].clear()
            await wait_for(lambda: len(runtime.calls) == 4)
            assert len(provider.active['a.txt']) == len(provider.active['b.txt']) == 2
            assert all(not service.workers[project, run].future.done() for run in runs)
        finally:
            await cleanup(service, planner, worker)
    asyncio.run(scenario())


def test_unconfirmed_stop_keeps_capacity_until_matching_stop_receipt(tmp_path):
    async def scenario():
        store, project, first, worker, planner, service, runtime, *_ = fixture(tmp_path, runtime=Runtime(pause=True))
        provider = Provider(service, tmp_path)
        second = await add_run(store, project, first, planner)
        third = await add_run(store, project, first, planner)
        try:
            await service.start_batch(project, [batch_item(run) for run in (first, second, third)])
            await wait_for(lambda: len(runtime.calls) == 2)
            provider.donor.confirm.clear()
            await service.stop(project, first)
            await wait_for(lambda: service.record(project, first)['phase'] == 'awaiting_stop')
            assert store.run(project, first)['state'] == 'STOPPING'
            assert not service.record(project, first)['stop_confirmed']
            initial = len(provider.probes)
            await wait_for(lambda: len(provider.probes) > initial)
            assert store.run(project, third)['state'] == 'QUEUED'
            assert len(provider.bootstrap.calls) == 2
            provider.donor.confirm.set()
            await service.tasks[project, first]
            await wait_for(lambda: len(runtime.calls) == 3)
            assert service.record(project, first)['stop_confirmed']
        finally:
            provider.donor.confirm.set()
            await cleanup(service, planner, worker)
    asyncio.run(scenario())


def test_capacity_rechecked_before_submission_when_external_sessions_appear(tmp_path):
    async def scenario():
        store, project, run, worker, planner, service, _, *_ = fixture(tmp_path)
        provider = Provider(service, tmp_path)
        service.records.reserve(project, run, 'cpu', 1800, 'a.txt')
        provider.external['a.txt'] = ['verified-user/external-1', 'verified-user/external-2']
        try:
            await service._work((project, run), store.approved_snapshot(project, run), 'cpu', 1800)
            assert store.run(project, run)['state'] == 'QUEUED'
            assert service.record(project, run)['phase'] == 'queued'
            assert not provider.bootstrap.calls
            await service.stop(project, run)
            assert not provider.donor.calls
        finally:
            await cleanup(service, planner, worker)
    asyncio.run(scenario())


def test_durable_reservations_across_projects_recover_without_resubmission(tmp_path):
    async def scenario():
        store, project, first, worker, planner, service, _, *_ = fixture(tmp_path)
        provider = Provider(service, tmp_path)
        second_project, second = approved_run(store)
        third = await add_run(store, project, first, planner)
        service.records.reserve(project, first, 'cpu', 1800, 'a.txt')
        service.records.reserve(second_project, second['id'], 'cpu', 1800, 'a.txt')
        for key in ((project, first), (second_project, second['id'])):
            service.view.root(*key).mkdir(parents=True, exist_ok=True)
        service.records.update(project, first, state='UNKNOWN', phase='unknown')
        recovered = WorkingService(planner, service.config, service.view, donor=service.donor, stop_seconds=.01, poll_seconds=.01)
        try:
            assert (await recovered.start(project, third, account='a.txt'))['state'] == 'QUEUED'
            assert recovered._account_occupancy('a.txt', {'active_session_count':0}) == 2
            await recovered.recover()
            await recovered.tasks[project, first]
            await recovered.tasks[second_project, second['id']]
            assert service.record(project, first)['stop_confirmed']
            assert service.record(second_project, second['id'])['stop_confirmed']
            assert not any(body.get('request_id') in {first, second['id']} for _, body in provider.bootstrap.calls)
            await wait_for(lambda: service.record(project, third)['stop_confirmed'])
        finally:
            await recovered.close(1)
            await cleanup(service, planner, worker)
    asyncio.run(scenario())


@pytest.mark.parametrize('readiness', ['busy', 'needs_login'])
def test_one_external_session_allows_another_run_with_cookie_gate(tmp_path, readiness):
    async def scenario():
        items, auth = cookie_fixture(tmp_path, readiness=readiness, after='busy', active_count=1)
        store, project, run, worker, planner, service, _, bootstrap, _ = items
        try:
            assert (await service.start(project, run, account='chosen.txt'))['state'] == 'STARTING'
            await service.tasks[project, run]
            assert store.run(project, run)['state'] == 'COMPLETED'
            assert len(bootstrap.calls) == 1
            assert auth['events'].count('login') == (1 if readiness == 'needs_login' else 0)
        finally:
            await cleanup(service, planner, worker)
    asyncio.run(scenario())


def test_parallel_report_jobs_use_run_workers_and_cancel_independently(tmp_path):
    class ReportRuntime(Runtime):
        def __init__(self):
            super().__init__()
            self.queries, self.release = [], threading.Event()

        def run(self, request, progress, cancelled):
            if request.role != 'mvp1_search_query':
                return super().run(request, progress, cancelled)
            self.queries.append(request)
            while not self.release.wait(.01):
                if cancelled():
                    raise RuntimeError('fixture report cancelled')
            return SimpleNamespace(text=json.dumps({'response':'# Local report\nRun '+request.request_id}), files={})

    async def scenario():
        runtime = ReportRuntime()
        store, project, base, worker, planner, service, *_ = fixture(tmp_path, runtime=runtime)
        Provider(service, tmp_path)
        service.config.codex_model = 'fixture-model'
        first = await add_run(store, project, base, planner, research={'report':True})
        second = await add_run(store, project, base, planner, research={'report':True})
        try:
            await service.start_batch(project, [batch_item(first), batch_item(second)])
            await wait_for(lambda: len(runtime.queries) == 2)
            assert worker.future is None
            assert all(service.workers[project, run].state['role'] == 'mvp1_search_query' for run in (first, second))
            await service.stop(project, first)
            await service.tasks[project, first]
            assert store.run(project, first)['state'] == 'CANCELLED'
            assert not service.workers[project, second].cancelled.is_set()
            runtime.release.set()
            await service.tasks[project, second]
            assert store.run(project, second)['state'] == 'COMPLETED'
            assert second in (service.view.root(project, second)/'research/report.md').read_text()
        finally:
            runtime.release.set()
            await cleanup(service, planner, worker)
    asyncio.run(scenario())


def test_http_batch_starts_three_concurrent_runs_on_two_accounts(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from test_session_recovery import application, wait_until
    runtime = Runtime(pause=True)
    app = application(tmp_path, runtime, Bootstrap(), monkeypatch, donor=Donor())
    store = app.state.store
    save_idea = store.save_idea
    def csv_idea(*args, **kwargs):
        # This fixture only writes CSV; concurrency/account admission is
        # independent of benchmark selection for Training/Research.
        return save_idea(*args, **{'mode': 'etc', 'desired_output': 'CSV fixture output', **kwargs})
    monkeypatch.setattr(store, 'save_idea', csv_idea)
    project, first = approved_run(store)
    runs = [first['id']]
    approved = store.approved_snapshot(project, first['id'])
    for _ in range(3):
        idea = store.save_idea(project, 'HTTP parallel fixture')
        context = store.context_snapshot(project, idea['id'], [row['id'] for row in approved['snapshot']['resources']])
        proposal = store.save_proposal(project, idea['id'], approved['body'], context)
        runs.append(store.approve_proposal(project, proposal, 1, context['context_sha256'])['id'])
    with TestClient(app) as client:
        Provider(app.state.working, tmp_path)
        base = f'/api/projects/{project}/runs'
        response = client.post(base+'/batch', json={'runs':[batch_item(run, 'a.txt' if i < 3 else 'b.txt')
                                                           for i, run in enumerate(runs)]})
        assert response.status_code == 202
        assert [row['state'] for row in response.json()['runs']] == ['STARTING', 'STARTING', 'QUEUED', 'STARTING']
        wait_until(lambda: len(runtime.calls), lambda count: count == 3)
        assert all(client.get(base+'/'+run).json()['state'] == 'WORKING' for run in (runs[0], runs[1], runs[3]))
        assert client.post(base+'/'+runs[2]+'/stop').json()['state'] == 'CANCELLED'
        for run in (runs[0], runs[1], runs[3]):
            assert client.post(base+'/'+run+'/stop').status_code == 202
        for run in runs:
            detail = wait_until(lambda: client.get(base+'/'+run).json(), lambda row: row['working']['stop_confirmed'])
            assert detail['state'] == 'CANCELLED'
