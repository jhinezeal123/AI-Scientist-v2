import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_scientist.workbench.collection import (
    MAX_REPORT_ATTEMPTS,
    RunResultsService,
    _report_prompt,
    validate_manifest,
    validate_run_outputs,
)
from ai_scientist.workbench.implementation import ImplementationService
from ai_scientist.workbench.journal import restore_journal
from ai_scientist.workbench.monitor import IDENTITY, RunMonitor
from ai_scientist.workbench.monitor_store import MonitorStore
from ai_scientist.workbench.models import ReportPayload, validate_result
from ai_scientist.workbench.service import PlanningService
from ai_scientist.workbench.store import canonical
from ai_scientist.workbench.worker import RuntimeWorker
from test_implementation import Runtime, setup
from test_planning import request_type


class ReportWorker:
    def __init__(self, *, fail=None):
        self.calls = []
        self.fail = fail
        self.future = None
        self.state = {'status': 'idle'}

    async def run(self, request, *, on_result=None):
        self.calls.append(request)
        self.state = {'status': 'running', 'request_id': request.request_id, 'role': request.role}
        assert request.role == 'mvp0_report'
        assert 'VALIDATED FACTS' in request.prompt
        assert 'outer JSON object with keys text and files' in request.prompt
        assert 'Do not return the report object directly at the outer level' in request.prompt
        if self.fail:
            self.state = {'status': self.fail}
            if self.fail == 'unknown':
                raise RuntimeError('fixture uncertain report worker')
            raise ValueError('fixture known report failure')
        payload = ReportPayload(
            summary='One measured result was recorded.',
            interpretation='The final value follows the approved minimization direction.',
            limitations=['This small fixture is not a leaderboard result.'],
            suggested_next=['Review the saved evidence before another experiment.'],
            evidence_refs=['output/result.json'],
        )
        if on_result is not None:
            await on_result(payload)
        self.state = {'status': 'completed'}
        return SimpleNamespace(term_out=['report complete'], exec_time=0.1, exc_type=None), payload


def make_receipt(root, pinned, result, metrics, runner_log):
    output = root / 'output'
    output.mkdir(parents=True, exist_ok=True)
    files = {
        'output/result.json': json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8'),
        'output/metrics.json': json.dumps(metrics, ensure_ascii=False, allow_nan=False).encode('utf-8'),
        'output/runner.log': runner_log.encode('utf-8'),
    }
    for path, data in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest = [{'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                for name, data in files.items()]
    return {'identity': {**{key: pinned[key] for key in IDENTITY}, 'status': 'COMPLETE',
                         'observed_at': '2026-10-06T00:00:00Z'}, 'manifest': manifest}


def prepared(tmp_path, monkeypatch, *, report_worker=None):
    monkeypatch.chdir(tmp_path)
    store, project, run, worker, planner, implementation = setup(tmp_path, Runtime())

    async def code():
        await implementation.start(project, run['id'])
        await planner.task

    asyncio.run(code())
    run = store.run(project, run['id'])
    approved = store.implementation_snapshot(project, run['id'], read_only=True)
    root = implementation.root(project, run['id'])
    context = json.loads((root / 'context.json').read_text(encoding='utf-8'))
    pinned = {'account': 'selected', 'username': 'verified-user',
              'kernel_ref': 'verified-user/ailab-' + run['id'], 'version': 1,
              'kernel_id': 11, 'script_version_id': 12, 'session_id': 13,
              'code_sha256': run['code_sha256'], 'context_sha256': approved['context_sha256'],
              'submit_attempts': 1, 'status': 'COMPLETE'}
    metric_name = approved['body']['metric']['name']
    point = {'step': 1, 'epoch': 1, 'elapsed_seconds': 0.1, 'total_steps': 1,
             'metrics': {metric_name: 1.25}}
    observed = {'train_sample_ids': ['train-a'], 'validation_sample_ids': ['valid-b'],
                'train_images': 1, 'validation_images': 1}
    result = {'schema_version': 1, 'run_id': run['id'], 'proposal_id': run['proposal_id'],
              'proposal_version': run['proposal_version'], 'code_sha256': run['code_sha256'],
              'context_sha256': approved['context_sha256'], 'data_refs': context['data_refs'],
              'split': {'approved': context['split'], 'observed': observed}, 'seed': context['config']['seed'],
              'metric': context['metric'], 'measurements': {metric_name: 1.25}, 'artifacts': [],
              'config': context['config'], 'elapsed_seconds': 0.2, 'environment': {'python': '3.12'}}
    runner_log = 'AILAB_METRIC ' + json.dumps(point, allow_nan=False) + '\nAILAB_COMPLETE ' + run['id'] + '\n'
    receipt = make_receipt(root, pinned, result, [point], runner_log)
    with store.connection(project) as connection:
        connection.execute('UPDATE runs SET state=?,identity_json=? WHERE id=?',
                           ('COLLECTING', canonical(pinned), run['id']))
    cache = MonitorStore(store)
    snapshot = {'records': [{'data': runner_log, 'stream_name': 'stdout', 'time': 1.0}],
                'complete': True, 'terminal': True, 'truncated': False,
                'identity': {**{key: pinned[key] for key in IDENTITY}, 'status': 'COMPLETE'},
                'observed_at': '2026-10-06T00:00:00Z', 'source': 'fixture'}
    cache.merge(project, run['id'], snapshot, metric_name, approved['body']['metric']['direction'])

    class Submission:
        def __init__(self):
            self.store = store
            self.implementation = implementation
            self.read_lock = asyncio.Lock()
            self.calls = []

        async def call(self, name, arguments, timeout=120):
            self.calls.append((name, arguments))
            assert name == 'workbench_collect_outputs'
            assert arguments['account'] == 'selected'
            assert arguments['pinned_identity']['session_id'] == 13
            return receipt

    submission = Submission()
    report_worker = report_worker or ReportWorker()
    service = RunResultsService(submission, report_worker, SimpleNamespace(request_type=request_type))
    return {'store': store, 'project': project, 'run': run, 'approved': approved, 'root': root,
            'pinned': pinned, 'receipt': receipt, 'result': result, 'metrics': [point],
            'runner_log': runner_log, 'snapshot': snapshot, 'cache': cache, 'submission': submission,
            'implementation': implementation, 'planner': planner, 'worker': worker,
            'report_worker': report_worker, 'service': service}


def test_report_prompt_and_outer_runtime_envelope_validate_inner_payload(tmp_path):
    prompt = _report_prompt({'evidence_refs': ['output/result.json']})
    assert 'outer JSON object with keys text and files' in prompt
    assert 'JSON-encoded report object with keys summary, interpretation, limitations' in prompt
    payload = {
        'summary': 'One measured result was recorded.',
        'interpretation': 'The approved metric was measured.',
        'limitations': ['This fixture is not a leaderboard result.'],
        'suggested_next': ['Review the evidence.'],
        'evidence_refs': ['output/result.json'],
    }
    # Codex's CLI envelope has the report JSON in text and an empty files object.
    outer = {'text': json.dumps(payload, ensure_ascii=False), 'files': {}}
    result = SimpleNamespace(text=outer['text'], files=outer['files'])
    validated = validate_result('mvp0_report', result)
    assert validated == ReportPayload(**payload)


def test_runtime_persists_validated_report_before_marking_worker_completed(tmp_path):
    payload = {
        'summary': 'One measured result was recorded.',
        'interpretation': 'The approved metric was measured.',
        'limitations': [],
        'suggested_next': [],
        'evidence_refs': ['output/result.json'],
    }

    class Runtime:
        def run(self, request, progress, cancelled):
            return SimpleNamespace(text=json.dumps(payload), files={})

    worker = RuntimeWorker(Runtime(), tmp_path / 'runtime-state.json')
    request = request_type('report-request', 'mvp0_report', 'report', tmp_path,
                           timeout_seconds=5, max_output_bytes=10_000)
    saved = tmp_path / 'report-result.json'

    async def run():
        async def persist(value):
            assert worker.state['status'] == 'running'
            saved.write_text(value.model_dump_json(), encoding='utf-8')

        await worker.run(request, on_result=persist)

    asyncio.run(run())
    assert worker.state['status'] == 'completed'
    assert saved.is_file()


def test_manifest_rejects_wrong_identity_unsafe_and_missing_files():
    pin = {'account': 'selected', 'username': 'user', 'kernel_ref': 'user/ailab-' + 'a' * 32,
           'version': 1, 'kernel_id': 11, 'script_version_id': 12, 'session_id': 13}
    manifest = [{'path': name, 'bytes': 1, 'sha256': 'a' * 64}
                for name in ('output/result.json', 'output/metrics.json', 'output/runner.log')]
    response = {'identity': {**pin, 'status': 'COMPLETE'}, 'manifest': manifest}
    assert len(validate_manifest(response, pin)) == 3
    with pytest.raises(ValueError, match='identity'):
        validate_manifest({**response, 'identity': {**pin, 'session_id': 99, 'status': 'COMPLETE'}}, pin)
    unsafe = {**response, 'manifest': [{**manifest[0], 'path': 'output/../escape'}, *manifest[1:]]}
    with pytest.raises(ValueError, match='unsafe'):
        validate_manifest(unsafe, pin)
    missing = {**response, 'manifest': manifest[:2]}
    with pytest.raises(ValueError, match='missing'):
        validate_manifest(missing, pin)


@pytest.mark.parametrize('failure', ['tampered_hash', 'wrong_run', 'missing_metric', 'source_hash', 'log_mismatch'])
def test_collector_rejects_mismatched_result_hash_metric_or_logs(tmp_path, monkeypatch, failure):
    f = prepared(tmp_path, monkeypatch)
    response = f['receipt']
    terminal = f['cache'].completed_snapshot(f['project'], f['run']['id'])
    if failure == 'tampered_hash':
        path = f['root'] / 'output/runner.log'
        path.write_text(path.read_text(encoding='utf-8') + 'changed', encoding='utf-8')
    elif failure == 'wrong_run':
        altered = dict(f['result'], run_id='f' * 32)
        response = make_receipt(f['root'], f['pinned'], altered, f['metrics'], f['runner_log'])
    elif failure == 'missing_metric':
        altered = dict(f['result'], measurements={})
        response = make_receipt(f['root'], f['pinned'], altered, f['metrics'], f['runner_log'])
    elif failure == 'source_hash':
        (f['root'] / 'source/workload.py').write_text('def changed(): pass\n', encoding='utf-8')
    elif failure == 'log_mismatch':
        point = dict(f['metrics'][0], metrics={f['approved']['body']['metric']['name']: 9.0})
        bad_log = 'AILAB_METRIC ' + json.dumps(point) + '\nAILAB_COMPLETE ' + f['run']['id'] + '\n'
        terminal = {**terminal, 'records': [{'data': bad_log, 'stream_name': 'stdout'}]}
    with pytest.raises(ValueError):
        validate_run_outputs(f['root'], f['run'], f['approved'], f['pinned'], response, terminal)


def test_remote_success_stays_collecting_when_report_worker_is_interrupted_then_restart_resumes(tmp_path, monkeypatch):
    f = prepared(tmp_path, monkeypatch, report_worker=ReportWorker(fail='interrupted'))
    async def check():
        result = await f['service'].collect_and_report(f['project'], f['run']['id'])
        assert result['state'] == 'COLLECTING'
        assert f['store'].run(f['project'], f['run']['id'])['state'] == 'COLLECTING'
        assert not (f['root'] / 'report.md').exists()
        assert not (f['root'] / 'report-result.json').exists()
        assert f['report_worker'].calls[0].role == 'mvp0_report'
        assert not any(name == 'push_notebook' for name, _ in f['submission'].calls)

        state_path = f['root'] / 'collection-state.json'
        state = json.loads(state_path.read_text(encoding='utf-8'))
        assert state['phase'] == 'retry_wait' and state['report_attempts'] == 1
        state['retry_after'] = '2000-01-01T00:00:00+00:00'
        state_path.write_text(json.dumps(state), encoding='utf-8')
        restarted_worker = ReportWorker()
        restarted_worker.state = {'status': 'interrupted',
                                  'request_id': state['request_id'], 'role': 'mvp0_report'}
        restarted = RunResultsService(f['submission'], restarted_worker, SimpleNamespace(request_type=request_type))
        monitor = RunMonitor(f['submission'], restarted)
        await monitor._discover_once()
        await asyncio.gather(*monitor.tasks.values())
        saved = f['store'].run(f['project'], f['run']['id'])
        assert saved['state'] == 'COMPLETED' and saved['report_path'] == 'report.md'
        assert saved['node_id'] and saved['node_json']
        assert len(restarted_worker.calls) == 1
        collection_calls = len(f['submission'].calls)
        assert await restarted.collect_and_report(f['project'], f['run']['id']) == {'run_id': f['run']['id'], 'state': 'COMPLETED'}
        assert len(f['submission'].calls) == collection_calls and len(restarted_worker.calls) == 1
        assert f['implementation'].detail(f['project'], f['run']['id'])['result_metric']['final_value'] == 1.25
        pinned_idea = f['approved']['snapshot']['idea']
        pinned_resource = f['approved']['snapshot']['resources'][0]
        with f['store'].connection(f['project']) as connection:
            connection.execute('UPDATE ideas SET text=? WHERE id=?', ('MUTATED LIVE IDEA', pinned_idea['id']))
            connection.execute('UPDATE resources SET title=? WHERE id=?', ('MUTATED LIVE SOURCE', pinned_resource['id']))
        history_entry = next(item for item in f['implementation'].history(f['project'])['runs']
                             if item['id'] == f['run']['id'])
        assert history_entry['idea_id'] is not None and history_entry['proposal_version'] == 1
        assert history_entry['idea_text'] == pinned_idea['text']
        assert history_entry['idea_text'] != 'MUTATED LIVE IDEA'
        assert history_entry['proposal_objective'] == f['approved']['body']['objective']
        assert history_entry['purpose'] == f['approved']['body']['objective']
        expected_refs = [resource for resource in f['approved']['snapshot']['resources']
                         if resource['id'] in f['approved']['body']['data_refs']]
        assert history_entry['source_refs'] == [
            {key: resource[key] for key in ('id', 'title', 'kind', 'version', 'content_sha256')}
            for resource in expected_refs
        ]
        assert all(source['title'] != 'MUTATED LIVE SOURCE' for source in history_entry['source_refs'])
        assert history_entry['code_sha256'] == f['run']['code_sha256']
        assert history_entry['report_available'] is True
        assert {'source/workload.py', 'notebook.ipynb', 'result-facts.json', 'report.md'} <= set(history_entry['artifacts'])
        journal = restore_journal(json.loads((f['root'] / 'journal.json').read_text(encoding='utf-8')))
        node = next(item for item in journal.nodes if item.id == saved['node_id'])
        assert node.metric.value == 1.25 and node.exp_results_dir.endswith('output')
        assert 'output/metrics.json' in f['implementation'].detail(f['project'], f['run']['id'])['artifacts']
        await monitor.close()
        await f['planner'].close(); await f['worker'].close(1)
    asyncio.run(check())


def test_uncertain_report_worker_is_never_retried_automatically(tmp_path, monkeypatch):
    f = prepared(tmp_path, monkeypatch, report_worker=ReportWorker(fail='unknown'))

    async def check():
        result = await f['service'].collect_and_report(f['project'], f['run']['id'])
        state = json.loads((f['root'] / 'collection-state.json').read_text(encoding='utf-8'))
        assert result['state'] == 'COLLECTING'
        assert state['phase'] == 'report_uncertain' and state['report_attempts'] == 1
        assert not f['service'].retry_due(f['project'], f['run']['id'])
        await f['service'].collect_and_report(f['project'], f['run']['id'])
        assert len(f['report_worker'].calls) == 1
        assert not (f['root'] / 'report.md').exists()
        await f['planner'].close(); await f['worker'].close(1)
    asyncio.run(check())


def test_report_attempt_count_is_durable_and_automatic_retries_are_bounded(tmp_path, monkeypatch):
    f = prepared(tmp_path, monkeypatch, report_worker=ReportWorker(fail='failed'))

    async def check():
        state_path = f['root'] / 'collection-state.json'
        for attempt in range(1, MAX_REPORT_ATTEMPTS + 1):
            result = await f['service'].collect_and_report(f['project'], f['run']['id'])
            state = json.loads(state_path.read_text(encoding='utf-8'))
            assert result['state'] == 'COLLECTING'
            assert state['report_attempts'] == attempt
            if attempt < MAX_REPORT_ATTEMPTS:
                state['retry_after'] = '2000-01-01T00:00:00+00:00'
                state_path.write_text(json.dumps(state), encoding='utf-8')
        state = json.loads(state_path.read_text(encoding='utf-8'))
        assert state['phase'] == 'retry_exhausted'
        assert len(f['report_worker'].calls) == MAX_REPORT_ATTEMPTS
        assert not f['service'].retry_due(f['project'], f['run']['id'])
        await f['service'].collect_and_report(f['project'], f['run']['id'])
        assert len(f['report_worker'].calls) == MAX_REPORT_ATTEMPTS
        await f['planner'].close(); await f['worker'].close(1)
    asyncio.run(check())


def test_completed_worker_without_durable_report_result_is_not_replayed(tmp_path, monkeypatch):
    f = prepared(tmp_path, monkeypatch)
    state_path = f['root'] / 'collection-state.json'
    request_id = 'report-request-completed'
    state_path.write_text(json.dumps({
        'phase': 'REPORTING', 'request_id': request_id, 'report_attempts': 1,
        'facts_sha256': 'a' * 64,
    }), encoding='utf-8')
    f['report_worker'].state = {'status': 'completed', 'request_id': request_id, 'role': 'mvp0_report'}

    async def check():
        await f['service'].collect_and_report(f['project'], f['run']['id'])
        state = json.loads(state_path.read_text(encoding='utf-8'))
        assert state['phase'] == 'report_result_missing'
        assert f['report_worker'].calls == []
        assert not f['service'].retry_due(f['project'], f['run']['id'])
        await f['planner'].close(); await f['worker'].close(1)
    asyncio.run(check())


def test_persisted_report_result_is_not_repeated_after_restart(tmp_path, monkeypatch):
    f = prepared(tmp_path, monkeypatch)
    original = f['store'].complete_collected_run
    first = {'raise': True}
    def interrupted(*args, **kwargs):
        if first['raise']:
            first['raise'] = False
            raise RuntimeError('fixture restart between report file and DB state')
        return original(*args, **kwargs)
    f['store'].complete_collected_run = interrupted

    async def check():
        first_result = await f['service'].collect_and_report(f['project'], f['run']['id'])
        assert first_result['state'] == 'COLLECTING'
        assert (f['root'] / 'report-result.json').is_file() and (f['root'] / 'report.md').is_file()
        previous_calls = len(f['report_worker'].calls)
        state_path = f['root'] / 'collection-state.json'
        state = json.loads(state_path.read_text(encoding='utf-8'))
        state['retry_after'] = '2000-01-01T00:00:00+00:00'
        state_path.write_text(json.dumps(state), encoding='utf-8')
        restarted_worker = ReportWorker()
        restarted = RunResultsService(f['submission'], restarted_worker, SimpleNamespace(request_type=request_type))
        monitor = RunMonitor(f['submission'], restarted)
        await monitor._discover_once()
        await asyncio.gather(*monitor.tasks.values())
        assert f['store'].run(f['project'], f['run']['id'])['state'] == 'COMPLETED'
        assert len(f['report_worker'].calls) == previous_calls
        assert restarted_worker.calls == []
        await monitor.close()
        await f['planner'].close(); await f['worker'].close(1)
    asyncio.run(check())
