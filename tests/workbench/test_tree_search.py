"""Single-run integration evidence for the former search entry point; local only."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json

import pytest

from ai_scientist.workbench.agents.codex import parse_codex_jsonl
from ai_scientist.workbench.journal import restore_journal
from ai_scientist.workbench.named_paths import filesystem_path
from test_working import Runtime, fixture, wait_for


@pytest.fixture(autouse=True)
def workspace_cwd(tmp_path, monkeypatch):
    # Upstream Node serializes experiment paths relative to the launch directory.
    monkeypatch.chdir(tmp_path)


@asynccontextmanager
async def working_fixture(tmp_path, runtime):
    items = fixture(tmp_path, runtime=runtime)
    _, _, _, worker, planner, service, _, _, _ = items
    try:
        yield items
    finally:
        await service.close(2)
        await planner.close()
        await worker.close(2)


def assert_stopped_run(service, project, run, state):
    detail = service.detail(project, run)
    assert detail['state'] == state, detail
    assert detail['working']['stop_confirmed']
    assert detail['working']['agent_called'] == detail['coder_calls'] == 1
    root = service.view.root(project, run)
    receipt = json.loads((root / 'working-stop.json').read_text(encoding='utf-8'))
    assert receipt['session_id'] == run
    assert receipt['notebook_ref'] == detail['working']['notebook_ref']
    assert receipt['status'] == 'complete' and receipt['stopped'] is True
    assert 'working-stop.json' in detail['artifacts']
    assert not any('terminal-access' in name for name in detail['artifacts'])
    assert not (root / 'working-agent/terminal-access.json').exists()
    memory = json.loads((root / 'memory_journal.json').read_text(encoding='utf-8'))
    assert memory['run_id'] == run and memory['state'] == state
    assert memory['stop_confirmed'] is True
    assert 'search' not in detail
    assert not (root / 'logs/0-run/search-state.json').exists()
    return detail, root


def assert_verified_files(root, detail):
    manifest = json.loads((root / 'working-manifest.json').read_text(encoding='utf-8'))
    assert manifest['command_count'] == 1
    assert {item['path'] for item in manifest['files']} == {'source/workload.py', 'output/test.csv'}
    for item in manifest['files']:
        data = (root / item['path']).read_bytes()
        assert len(data) == item['bytes']
        assert hashlib.sha256(data).hexdigest() == item['sha256']
        assert item['path'] in detail['artifacts']
    assert (root / 'output/test.csv').read_bytes() == b'id,prediction\n1,7\n'
    assert (root / 'source/workload.py').read_bytes() == b'print("fixture")\n'
    return manifest


def test_single_working_ignores_legacy_search_budget_and_preserves_layout_and_retry(tmp_path):
    async def check():
        runtime = Runtime()
        async with working_fixture(tmp_path, runtime) as items:
            store, project, run, worker, _, service, _, bootstrap, donor = items
            approved = store.approved_snapshot(project, run)
            # Old callers may still send search budgets; they must not create
            # hidden experiments or invoke stages outside the approved run.
            await service.start(project, run, search={'stage_iterations': [2, 2, 2, 1], 'debug_prob': 1.0})
            await service.tasks[project, run]
            detail, root = assert_stopped_run(service, project, run, 'COMPLETED')
            assert detail['working']['summary']['succeeded'] is True
            assert [(call.request_id, call.role) for call in runtime.calls] == [(run, 'mvp0_working')]
            assert len(donor.opens) == len(bootstrap.calls) == 1
            assert [item['id'] for item in store.history(project)['runs']] == [run]
            assert worker.future is None and worker.state == {'status': 'idle'}
            assert detail['artifact_dir'].startswith('experiment/') and detail['artifact_dir'].endswith('_attempt_0')
            assert root.parent == filesystem_path(store.directory(project) / 'experiment')
            assert not (tmp_path / 'experiments').exists()
            assert all((root / path).is_file() for path in ('idea.md', 'idea.json', 'journal.json', 'execution.json', 'memory_journal.json'))
            pinned = json.loads((runtime.calls[0].workdir / 'working-request.json').read_text(encoding='utf-8'))
            assert pinned['approved']['body'] == approved['body']
            assert pinned['approved']['context_sha256'] == approved['context_sha256']
            assert 'search' not in pinned
            assert not (root / 'query-agent').exists() and not (root / 'report.md').exists()
            saved = json.loads((root / 'journal.json').read_text(encoding='utf-8'))
            journal = restore_journal(saved)
            assert saved['run_id'] == run and saved['parent_run_id'] is None
            assert len(journal) == 1 and journal[0].id == run
            assert journal[0].parent is None and not journal[0].children and not journal[0].is_buggy
            assert 'print("fixture")' in journal[0].code
            assert store.run(project, run)['node_id'] == run
            execution = json.loads((root / 'execution.json').read_text(encoding='utf-8'))
            assert execution['run_id'] == run and execution['result']['succeeded'] is True
            assert len(execution['commands']) == 1
            assert execution['commands'][0]['returncode'] == 0
            assert 'fixture terminal output' in execution['commands'][0]['output']
            assert_verified_files(root, detail)
            before = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                      for name in ('source/workload.py', 'output/test.csv', 'journal.json', 'execution.json', 'working-manifest.json')}

            new = await service.retry(project, run, 'e' * 32)
            assert new['id'] != run and store.run(project, new['id'])['parent_run_id'] == run
            await service.start(project, new['id'], search={'stage_iterations': [1, 1, 1, 1]})
            await service.tasks[project, new['id']]
            retry_detail, retry_root = assert_stopped_run(service, project, new['id'], 'COMPLETED')
            assert retry_root != root and retry_root.name.endswith('_attempt_1')
            assert [(call.request_id, call.role) for call in runtime.calls] == [(run, 'mvp0_working'), (new['id'], 'mvp0_working')]
            assert [body['request_id'] for _, body in bootstrap.calls] == [run, new['id']]
            assert [session for session, _ in donor.opens] == [run, new['id']]
            assert all(terminal.stop_requested and terminal.closed for _, terminal in donor.opens)
            assert set(item['id'] for item in store.history(project)['runs']) == {run, new['id']}
            assert_verified_files(retry_root, retry_detail)
            assert before == {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in before}
            assert store.approved_snapshot(project, run) == approved
            assert json.loads((retry_root / 'memory_journal.json').read_text(encoding='utf-8'))['parent_run_id'] == run
            source = store.resources(project)[0]
            copies = [path for location in (root, retry_root)
                      for path in (location / 'working-agent/library').rglob('source.md')]
            assert len(copies) == 2 and all(path.is_file() for path in copies)
            store.delete_resource(project, source['id'])
            assert all(not path.exists() for path in copies)
            assert before == {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in before}
    asyncio.run(check())


def test_failed_working_records_one_buggy_node_and_stops_without_automatic_retry(tmp_path):
    class FailedResultRuntime(Runtime):
        def run(self, request, progress, cancelled):
            result = super().run(request, progress, cancelled)
            payload = json.loads(result.text)
            payload.update(succeeded=False, summary='Local fixture experiment failed')
            result.text = json.dumps(payload)
            return result

    async def check():
        runtime = FailedResultRuntime()
        async with working_fixture(tmp_path, runtime) as items:
            store, project, run, _, _, service, _, bootstrap, donor = items
            await service.start(project, run, search={'stage_iterations': [1, 1, 1, 1]})
            await service.tasks[project, run]
            detail, root = assert_stopped_run(service, project, run, 'FAILED')
            assert detail['working']['summary']['succeeded'] is False
            assert detail['working']['summary']['summary'] == 'Local fixture experiment failed'
            assert len(runtime.calls) == len(bootstrap.calls) == len(donor.opens) == 1
            assert runtime.calls[0].request_id == run and runtime.calls[0].role == 'mvp0_working'
            assert [item['id'] for item in store.history(project)['runs']] == [run]
            journal = restore_journal(json.loads((root / 'journal.json').read_text(encoding='utf-8')))
            assert len(journal) == 1 and journal[0].id == run and journal[0].is_buggy
            assert journal[0].parent is None and not journal[0].children
            assert json.loads((root / 'execution.json').read_text(encoding='utf-8'))['result']['succeeded'] is False
            assert_verified_files(root, detail)
            assert donor.opens[0][1].stop_requested and donor.opens[0][1].closed
    asyncio.run(check())


def test_stop_cancels_exact_working_worker_without_opening_another_session(tmp_path):
    async def check():
        runtime = Runtime(pause=True)
        async with working_fixture(tmp_path, runtime) as items:
            store, project, run, planner_worker, _, service, _, bootstrap, donor = items
            await service.start(project, run, search={'stage_iterations': [2, 2, 2, 1]})
            await wait_for(runtime.entered.is_set)
            run_worker = service.workers[project, run]
            assert run_worker is not planner_worker
            assert run_worker.future is not None and not run_worker.future.done()
            assert planner_worker.future is None and not planner_worker.cancelled.is_set()
            assert (await service.stop(project, run))['state'] == 'STOPPING'
            await asyncio.wait_for(service.tasks[project, run], 10)
            detail, root = assert_stopped_run(service, project, run, 'CANCELLED')
            assert detail['working']['summary']['succeeded'] is False
            assert run_worker.cancelled.is_set() and run_worker.closed
            assert not planner_worker.cancelled.is_set() and not planner_worker.closed
            assert len(runtime.calls) == len(bootstrap.calls) == len(donor.opens) == 1
            assert [body['request_id'] for _, body in bootstrap.calls] == [run]
            assert [session for session, _ in donor.opens] == [run]
            assert donor.opens[0][1].stop_requested and donor.opens[0][1].closed
            assert [item['id'] for item in store.history(project)['runs']] == [run]
            assert not (root / 'journal.json').exists()
    asyncio.run(check())


def test_codex_usage_is_measured_from_turn_event_for_search_roles():
    raw = '\n'.join(json.dumps(event) for event in [
        {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps({'response': 'fixture'})}},
        {'type': 'turn.completed', 'usage': {'input_tokens': 10, 'cached_input_tokens': 3, 'output_tokens': 2}}]).encode()
    result = parse_codex_jsonl(raw, role='mvp1_search_query')
    assert result['usage'] == {'input_tokens': 10, 'cached_input_tokens': 3, 'output_tokens': 2}
    assert json.loads(result['text']) == {'response': 'fixture'}


def test_late_working_final_keeps_verified_files_before_stop_without_claiming_success(tmp_path):
    class LateFinalRuntime(Runtime):
        def run(self, request, progress, cancelled):
            super().run(request, progress, cancelled)
            raise TimeoutError('Fixture final response exceeded its deadline')

    async def check():
        runtime = LateFinalRuntime()
        async with working_fixture(tmp_path, runtime) as items:
            store, project, run, _, _, service, _, bootstrap, donor = items
            await service.start(project, run, search={'stage_iterations': [1, 1, 1, 1]})
            await service.tasks[project, run]
            detail, root = assert_stopped_run(service, project, run, 'FAILED')
            assert detail['working']['summary']['succeeded'] is False
            assert 'Hết thời gian Working' in detail['working']['summary']['summary']
            assert len(runtime.calls) == len(bootstrap.calls) == len(donor.opens) == 1
            assert runtime.calls[0].request_id == run and runtime.calls[0].role == 'mvp0_working'
            assert [item['id'] for item in store.history(project)['runs']] == [run]
            assert_verified_files(root, detail)
            assert donor.opens[0][1].stop_requested and donor.opens[0][1].closed
            execution = json.loads((root / 'execution.json').read_text(encoding='utf-8'))
            assert execution['run_id'] == run and len(execution['commands']) == 1
            assert execution['commands'][0]['returncode'] == 0
            assert 'result' not in execution and not (root / 'journal.json').exists()
            assert store.run(project, run)['node_id'] is None
    asyncio.run(check())
