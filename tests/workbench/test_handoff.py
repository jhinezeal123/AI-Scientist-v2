"""T09 contracts at the GUI/API and frozen notebook handoff boundaries."""
import ast
import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import nbformat
import pytest
from pydantic import ValidationError

from ai_scientist.workbench.app import create_app
from ai_scientist.workbench.bundle import build_bundle
from ai_scientist.workbench.collection import _report_prompt
from ai_scientist.workbench.models import ReportPayload
from ai_scientist.workbench.notebook_runner import execute_workload
from ai_scientist.workbench.submission import sha
from ai_scientist.workbench.worker import RuntimeWorker
from test_implementation import SOURCE, Runtime, payload, setup
from test_planning import FakeRuntime, request_type
from test_submission import MCP, prepared


def notebook_context(path):
    notebook = nbformat.read(path, as_version=4)
    assignment = ast.parse(notebook.cells[1].source).body[1]
    return json.loads(ast.literal_eval(assignment.value.args[0]))


def test_generated_notebook_supplies_the_mount_contract_seen_by_the_coder(tmp_path):
    source = SOURCE.replace(
        '    emit(',
        "    assert context['runtime_contract']['input_mounts'] == context['input_mounts']\n"
        '    emit(',
    )
    store, project, run, worker, planner, implementation = setup(tmp_path, Runtime())
    root = tmp_path / 'bundle'
    approved = store.approved_context(project, run['id'])
    item = payload(source)
    assert build_bundle(root, store.run(project, run['id']), approved, item, 'verified-user')['pass']
    context = json.loads((root / 'context.json').read_text(encoding='utf-8'))
    assert context == notebook_context(root / 'notebook.ipynb')
    assert context['runtime_contract']['input_mounts'] == ['/kaggle/input/competitions/fixture-data']
    context['output_dir'] = str(tmp_path / 'fixture-output')
    execute_workload(context, source)  # Instrumented fixture only; no torch/data/provider calls.
    result = json.loads((tmp_path / 'fixture-output/result.json').read_text(encoding='utf-8'))
    assert result['run_id'] == run['id'] and result['code_sha256'] == context['code_sha256']
    assert result['input_mounts'] == context['runtime_contract']['input_mounts']
    assert 'AILAB_COMPLETE ' + run['id'] in (tmp_path / 'fixture-output/runner.log').read_text(encoding='utf-8')
    asyncio.run(worker.close(1))


def test_submit_handoff_restores_fixed_context_without_changing_coder_source(tmp_path):
    async def check():
        mcp = MCP()
        store, project, run, worker, planner, implementation, submission = await prepared(tmp_path, mcp)
        root = implementation.root(project, run['id'])
        original_code = (root / 'source/workload.py').read_bytes()
        # Simulate a previously built bundle that lacked the fixed runtime contract.
        context_path = root / 'context.json'
        context = json.loads(context_path.read_text(encoding='utf-8'))
        context.pop('runtime_contract')
        context_path.write_text(json.dumps(context), encoding='utf-8')
        manifest_path = root / 'bundle-manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['context.json'] = sha(context_path)
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        _, bundle, _, intent = submission.prepare(project, run['id'])
        frozen = json.loads((bundle / 'context.json').read_text(encoding='utf-8'))
        assert frozen == notebook_context(bundle / 'notebook.ipynb')
        assert frozen['runtime_contract']['input_mounts'] == frozen['input_mounts']
        assert (bundle / 'source/workload.py').read_bytes() == original_code
        assert intent['code_sha256'] == store.run(project, run['id'])['code_sha256']
        assert store.run(project, run['id'])['identity_json'] is None and mcp.calls == []
        await planner.close()
        await worker.close(1)
    asyncio.run(check())


def test_missing_or_unselected_data_is_rejected_before_any_agent_or_push(tmp_path):
    runtime = FakeRuntime()
    calls = []
    class NoWorkMCP:
        async def call_tool(self, name, arguments):
            calls.append(name)
            raise AssertionError('A rejected context cannot authorize provider work')
    @asynccontextmanager
    async def connection(config):
        yield NoWorkMCP(), ['push_notebook']
    config = SimpleNamespace(workspace_root=tmp_path, shutdown_seconds=2)
    bindings = SimpleNamespace(runtime=runtime, request_type=request_type)
    with TestClient(create_app(config, bindings=bindings, mcp_connection=connection)) as client:
        project = client.post('/api/projects', json={'name': 'T09 fixture'}).json()['id']
        base = '/api/projects/' + project
        idea = client.post(base + '/ideas', json={'text': 'Fixture idea'}).json()
        body = {'idea_id': idea['id'], 'resource_ids': []}
        assert client.post(base + '/plan', json=body).status_code == 422
        assert client.post(base + '/context', json=body).status_code == 422
        body['resource_ids'] = ['missing-source']
        assert client.post(base + '/plan', json=body).status_code == 404
        assert client.post(base + '/context', json=body).status_code == 404
        assert client.get(base + '/history').json() == {'proposals': [], 'runs': []}
        assert runtime.calls == [] and calls == []


def test_report_prompt_supplies_exact_types_and_inner_schema():
    prompt = _report_prompt({'evidence_refs': ['output/result.json']})
    encoded = prompt.split('REPORT PAYLOAD JSON SCHEMA:\n', 1)[1].split('\nVALIDATED FACTS:\n', 1)[0]
    schema = json.loads(encoded)
    assert schema == ReportPayload.model_json_schema()
    assert not schema['additionalProperties']
    assert schema['properties']['summary']['type'] == 'string'
    assert schema['properties']['limitations']['items']['type'] == 'string'
    assert 'plain string' in prompt and 'array of strings' in prompt


def test_invalid_report_records_field_types_without_private_inputs_or_unknown_keys(tmp_path):
    class InvalidReportRuntime:
        def run(self, request, progress, cancelled):
            payload = {'summary': {'secret': 'private-input'}, 'interpretation': 'fixture',
                       'limitations': 'wrong-list-type', 'suggested_next': [], 'evidence_refs': [],
                       'private-key': 'private-input'}
            return SimpleNamespace(text=json.dumps(payload), files={}, session_id='fixture-session')
    async def check():
        worker = RuntimeWorker(InvalidReportRuntime(), tmp_path / 'runtime-state.json')
        with pytest.raises(ValidationError):
            await worker.run(SimpleNamespace(request_id='report-fixture', role='mvp0_report'))
        saved = json.loads((tmp_path / 'runtime-state.json').read_text())
        assert saved['status'] == 'failed' and saved['session_id'] == 'fixture-session'
        assert saved['validation_errors'] == [
            {'field': 'summary', 'type': 'string_type'},
            {'field': 'limitations', 'type': 'list_type'},
            {'field': 'payload', 'type': 'extra_forbidden'},
        ]
        assert 'private-input' not in json.dumps(saved) and 'private-key' not in json.dumps(saved)
        await worker.close(1)
    asyncio.run(check())
