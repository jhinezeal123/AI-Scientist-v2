import asyncio
import json
from types import SimpleNamespace

import pytest

from ai_scientist.workbench.monitor import RunMonitor, IDENTITY
from ai_scientist.workbench.monitor_store import MonitorStore
from ai_scientist.workbench.store import ProjectStore, canonical
from test_implementation import approved_run


@pytest.fixture
def fixture(tmp_path):
    store = ProjectStore(tmp_path / 'projects')
    project, run = approved_run(store)
    return store, project, run['id'], MonitorStore(store)


def record(text):
    return {'data': text, 'stream_name': 'stdout', 'time': 1.0}


def snapshot(records, complete=False, terminal=False):
    return {'records': records, 'complete': complete, 'terminal': terminal,
            'identity': {'status': 'COMPLETE' if terminal else 'RUNNING'},
            'observed_at': '2026-10-06T00:00:00Z', 'source': 'fixture'}


def test_repeat_prefix_short_replay_and_persistence(fixture):
    store, project, run, cache = fixture
    a = record('A')
    for records in ([a], [a, a], [a, a], [a]):
        cache.merge(project, run, snapshot(records), 'score', 'minimize')
    page = cache.delta(project, run, limit=1)
    assert page['entries'] == [{'seq': 1, 'text': 'A', 'stream': 'stdout'}]
    assert page['has_more'] and page['next_cursor'] == '1:1'
    page2 = cache.delta(project, run, page['next_cursor'])
    assert page2['entries'][0]['seq'] == 2 and not page2['has_more']
    restarted = MonitorStore(ProjectStore(store.root))
    assert restarted.delta(project, run)['entries'] == cache.delta(project, run)['entries']
    assert restarted.delta(project, run, page2['next_cursor'])['entries'] == []


def test_generation_gap_and_authoritative_terminal_reconciliation(fixture):
    store, project, run, cache = fixture
    a, b = record('A'), record('B')
    cache.merge(project, run, snapshot([a, a]), 'score', 'minimize')
    cache.merge(project, run, snapshot([b]), 'score', 'minimize')
    reset = cache.delta(project, run, '1:2')
    assert reset['generation'] == 2 and reset['reset'] and reset['gap']
    cache.merge(project, run, snapshot([a, a, b], True, True), 'score', 'minimize')
    end = cache.delta(project, run, reset['next_cursor'])
    assert end['reset'] and end['generation'] == 3 and end['terminal'] and not end['gap']
    assert [entry['text'] for entry in end['entries']] == ['A', 'A', 'B']
    with store.connection(project) as connection:
        assert connection.execute('SELECT COUNT(*) FROM logs WHERE generation=1').fetchone()[0] == 2


@pytest.mark.parametrize('cursor', ['invalid', '1:-1', '1:99'])
def test_invalid_cursor(fixture, cursor):
    _, project, run, cache = fixture
    with pytest.raises(ValueError):
        cache.delta(project, run, cursor)


def test_measured_eta_and_invalid_telemetry(fixture):
    _, project, run, cache = fixture
    def point(step, elapsed):
        return record('AILAB_METRIC ' + json.dumps({'step': step, 'elapsed_seconds': elapsed,
                      'total_steps': 4, 'metrics': {'score': 10 / step}}))
    records = [point(1, 3)]
    cache.merge(project, run, snapshot(records), 'score', 'minimize')
    assert cache.delta(project, run)['eta_seconds'] is None
    records += [point(2, 8), point(2, 8)]
    cache.merge(project, run, snapshot(records), 'score', 'minimize')
    page = cache.delta(project, run)
    assert page['eta_seconds'] == 10 and len(page['points']) == 2 and len(page['entries']) == 3
    cache.failed_read(project, run, 'Read timeout')
    assert cache.delta(project, run)['eta_seconds'] is None
    records += [record('AILAB_METRIC {"step":1,"metrics":{"score":NaN}}')]
    cache.merge(project, run, snapshot(records), 'score', 'minimize')
    assert cache.delta(project, run)['telemetry_error']
    assert cache.delta(project, run)['eta_seconds'] is None


def test_restart_observer_exact_identity_no_duplicate_or_submit(fixture, tmp_path):
    store, project, run, cache = fixture
    pin = dict(zip(IDENTITY, ['alias', 'user', 'user/ailab-' + run, 1, 11, 12, 13]))
    pin['submit_attempts'] = 1
    with store.connection(project) as connection:
        connection.execute('UPDATE runs SET identity_json=?,state=? WHERE id=?', (canonical(pin), 'RUNNING', run))
    calls = []
    async def call(name, args, timeout):
        assert name == 'workbench_monitor_snapshot'
        assert args['pinned_identity'] == {key: pin[key] for key in IDENTITY}
        calls.append(name)
        result = snapshot([record('A'), record('A')], True, True)
        result['identity'] = {**pin, 'status': 'COMPLETE'}
        return result
    root = tmp_path / 'evidence'
    root.mkdir()
    cache.merge(project, run, snapshot([record('A')]), 'score', 'minimize')
    submission = SimpleNamespace(store=store, call=call, read_lock=asyncio.Lock(),
                                 implementation=SimpleNamespace(root=lambda *_: root))
    async def check():
        first = RunMonitor(submission)
        await first._watch(project, run, pin)
        assert store.run(project, run)['state'] == 'COLLECTING'
        assert len(first.cache.delta(project, run)['entries']) == 2
        restarted = RunMonitor(submission)
        await restarted._discover_once()
        assert restarted.tasks == {} and len(calls) == 1
        assert json.loads(store.run(project, run)['identity_json'])['submit_attempts'] == 1
        await first.close()
        await restarted.close()
    asyncio.run(check())


def test_discovery_one_observer_per_run_and_identity_mismatch(fixture, tmp_path):
    store, project, run, cache = fixture
    pin = dict(zip(IDENTITY, ['alias', 'user', 'user/ailab-' + run, 1, 11, 12, 13]))
    with store.connection(project) as connection:
        connection.execute('UPDATE runs SET identity_json=?,state=? WHERE id=?', (canonical(pin), 'RUNNING', run))
    async def check():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def call(name, args, timeout):
            calls.append(name)
            entered.set()
            await release.wait()
            result = snapshot([record('Untrusted')])
            result['identity'] = {**pin, 'session_id': 999, 'status': 'RUNNING'}
            return result
        submission = SimpleNamespace(store=store, call=call, read_lock=asyncio.Lock())
        monitor = RunMonitor(submission)
        await monitor._discover_once()
        await asyncio.wait_for(entered.wait(), 2)
        await monitor._discover_once()
        assert len(monitor.tasks) == 1 and calls == ['workbench_monitor_snapshot']
        release.set()
        for _ in range(200):
            await asyncio.sleep(.01)
            page = cache.delta(project, run)
            if page['error']:
                break
        assert page['run_state'] == 'UNKNOWN' and page['error'] and page['entries'] == []
        assert json.loads(store.run(project, run)['identity_json'])['session_id'] == 13
        await monitor.close()
    asyncio.run(check())


@pytest.mark.parametrize('observation_state', ['COLLECTING', 'UNKNOWN', 'RUNNING'])
def test_completed_run_cannot_be_downgraded_by_observer(fixture, observation_state):
    store, project, run, _ = fixture
    pin = dict(zip(IDENTITY, ['alias', 'user', 'user/ailab-' + run, 1, 11, 12, 13]))
    with store.connection(project) as connection:
        connection.execute('UPDATE runs SET identity_json=?,state=?,report_path=? WHERE id=?',
                           (canonical(pin), 'COMPLETED', 'report.md', run))
    before = store.run(project, run)
    assert store.submission_observed(project, run, observation_state, pin, 'Read failed') == 'COMPLETED'
    assert store.run(project, run) == before
    async def check():
        monitor = RunMonitor(SimpleNamespace(store=store))
        await monitor._discover_once()
        assert not monitor.tasks
        await monitor.close()
    asyncio.run(check())


def test_discovery_restarts_crashed_observer(fixture, tmp_path):
    store, project, run, cache = fixture
    pin = dict(zip(IDENTITY, ['alias', 'user', 'user/ailab-' + run, 1, 11, 12, 13]))
    with store.connection(project) as connection:
        connection.execute('UPDATE runs SET identity_json=?,state=? WHERE id=?', (canonical(pin), 'RUNNING', run))
    root = tmp_path / 'restart-evidence'
    root.mkdir()
    async def check():
        async def crash():
            raise RuntimeError('Fixture task crashed')
        calls = []
        async def call(name, args, timeout):
            calls.append(name)
            result = snapshot([record('Recovered')], True, True)
            result['identity'] = {**pin, 'status': 'COMPLETE'}
            return result
        submission = SimpleNamespace(store=store, call=call, read_lock=asyncio.Lock(),
                                     implementation=SimpleNamespace(root=lambda *_: root))
        monitor = RunMonitor(submission)
        dead = asyncio.create_task(crash())
        await asyncio.gather(dead, return_exceptions=True)
        monitor.tasks[(project, run)] = dead
        await monitor._discover_once()
        assert monitor.tasks[(project, run)] is not dead
        await asyncio.wait_for(monitor.tasks[(project, run)], 2)
        assert calls == ['workbench_monitor_snapshot']
        assert cache.delta(project, run)['entries'][0]['text'] == 'Recovered'
        await monitor.close()
    asyncio.run(check())


def test_oversized_metric_number_does_not_prevent_log_storage(fixture):
    _, project, run, cache = fixture
    bad = record('AILAB_METRIC ' + json.dumps({'step': 1, 'total_steps': 2,
                                             'elapsed_seconds': 1, 'metrics': {'score': 10**400}}))
    cache.merge(project, run, snapshot([bad, record('Done')], True, True), 'score', 'minimize')
    page = cache.delta(project, run)
    assert page['terminal'] and len(page['entries']) == 2 and not page['points']
    assert page['telemetry_error'] and page['error'] is None
