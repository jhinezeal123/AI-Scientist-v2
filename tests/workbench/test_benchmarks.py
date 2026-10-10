"""Benchmark contract, approval pinning and the full local Working journey."""
import asyncio
import base64
from contextlib import asynccontextmanager
import copy
import hashlib
import json
import threading
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_scientist.workbench.app import create_app
from ai_scientist.workbench.api import library_router
from ai_scientist.workbench.benchmarks import BenchmarkCatalog, BenchmarkDefinition, validate_benchmark_output
from ai_scientist.workbench.store import ProjectStore, StoreConflict
from test_planning import request_type
from test_working import Donor, Bootstrap

DEFINITION = {'metric': {'name': 'latency_ms', 'direction': 'minimize',
                         'definition': 'Median inference latency after 10 warmup requests'},
              'test_split': 'All rows in requests.csv are test requests', 'train_split': None}


def approve(store, project, idea):
    context = store.context_snapshot(project, idea['id'], [])
    body = {'needs_clarification': False, 'paraphrase': 'Prepare benchmark',
            'objective': 'Inference benchmark', 'implementation_steps': ['Prepare requests and evaluator'],
            'metric': DEFINITION['metric'], 'split': {'test': DEFINITION['test_split'], 'train': None}}
    proposal = store.save_proposal(project, idea['id'], body, context)
    return store.approve_proposal(project, proposal, 1, context['context_sha256'])


def package_files(definition=DEFINITION):
    return {'output/benchmark/benchmark.json': json.dumps({'schema_version': 1, 'definition': definition,
            'test_files': ['requests.csv'], 'train_files': [], 'evaluator_interface': 'python evaluate.py --result results.json'}).encode(),
            'output/benchmark/evaluate.py': b'# Fixture evaluator, no provider execution\n',
            'output/benchmark/requests.csv': b'id,prompt\n1,hello\n'}


def test_test_required_train_optional_and_package_hashes(tmp_path):
    assert BenchmarkDefinition.model_validate(DEFINITION).train_split is None
    for value in ('', '  '):
        with pytest.raises(ValueError):
            BenchmarkDefinition.model_validate({**DEFINITION, 'test_split': value})
        with pytest.raises(ValueError):
            BenchmarkDefinition.model_validate({**DEFINITION, 'metric': {**DEFINITION['metric'], 'definition': value}})
    with pytest.raises(ValueError, match='MLflow'):
        BenchmarkDefinition.model_validate({**DEFINITION, 'metric': {**DEFINITION['metric'], 'name': 'latency:ms'}})
    files = package_files()
    manifest = {'files': []}
    for name, data in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest['files'].append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    directory, digest = validate_benchmark_output(tmp_path, DEFINITION, manifest)
    assert directory.name == 'benchmark' and len(digest) == 64
    (directory / 'requests.csv').write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'):
        validate_benchmark_output(tmp_path, DEFINITION, manifest)


def test_structured_evaluator_interface_and_no_undeclared_public_files(tmp_path):
    files = package_files()
    config = json.loads(files['output/benchmark/benchmark.json'])
    config['evaluator_interface'] = {'function':'evaluate(predictions_path,test_path)',
        'cli':'python evaluate.py --predictions predictions.csv --test requests.csv'}
    files['output/benchmark/benchmark.json'] = json.dumps(config).encode()
    manifest = {'files': []}
    for name, data in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest['files'].append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    validate_benchmark_output(tmp_path, DEFINITION, manifest)
    private_log = tmp_path / 'output/benchmark/source/qa_evaluator_checks.json'
    private_log.parent.mkdir(parents=True)
    private_log.write_text('{}')
    with pytest.raises(ValueError, match='undeclared'):
        validate_benchmark_output(tmp_path, DEFINITION, manifest)


def test_catalog_requires_public_completed_and_freezes_reference(tmp_path):
    store = ProjectStore(tmp_path / 'projects')
    project = store.create_project('Benchmarks')['id']
    idea = store.save_idea(project, 'Prepare test workload', mode='benchmark', benchmark_definition=DEFINITION)
    run = approve(store, project, idea)
    catalog = BenchmarkCatalog(store)
    receipt = {'handle': 'fixture/benchmark', 'url': 'https://www.kaggle.com/datasets/fixture/benchmark',
               'version': 1, 'visibility': 'public', 'manifest_sha256': 'a' * 64, 'files': []}
    with pytest.raises(ValueError, match='public'):
        catalog.save(project, run['id'], 'Benchmark', DEFINITION, {**receipt, 'visibility': 'private'})
    catalog.save(project, run['id'], 'Benchmark', DEFINITION, receipt)
    assert catalog.list(project) == []
    with store.connection(project) as connection:
        connection.execute("UPDATE runs SET state='COMPLETED' WHERE id=?", (run['id'],))
    reference = catalog.require(project, run['id'])
    research = store.save_idea(project, 'Improve cache', benchmark_id=run['id'])
    context = store.context_snapshot(project, research['id'], [])
    assert context['snapshot']['idea']['benchmark'] == reference
    assert context['snapshot']['idea']['benchmark']['definition']['train_split'] is None
    with pytest.raises(StoreConflict, match='đóng băng'):
        catalog.save(project, run['id'], 'Benchmark', DEFINITION, {**receipt, 'version': 2})
    other = store.create_project('Other')['id']
    with pytest.raises(StoreConflict):
        store.save_idea(other, 'Cache', benchmark_id=run['id'])
    assert not store.can_delete_run(project, run['id'])
    store.set_deleted(project, 'ideas', research['id'])
    assert store.can_delete_run(project, run['id'])
    store.delete_run(project, run['id'])
    assert catalog.list(project) == []


class BenchmarkRuntime:
    def __init__(self, donor):
        self.donor = donor
        self.calls = []
    def run(self, request, progress, cancelled):
        self.calls.append(request)
        if request.role == 'mvp0_plan':
            context = json.loads(request.prompt.split('UNTRUSTED PROJECT CONTEXT:\n')[1])
            return SimpleNamespace(text=json.dumps({'needs_clarification': False, 'paraphrase': 'Inference benchmark',
                'objective': 'Create inference benchmark', 'implementation_steps': ['Prepare test and evaluator'],
                'data_refs': [], 'expected_outputs': ['Public dataset link']}), files={})
        terminal = self.donor.opens[-1][1]
        terminal.request('exec', command='fixture benchmark generation', timeout=2)
        for name, data in package_files().items():
            terminal.request('write', path=name, data=base64.b64encode(data).decode())
        return SimpleNamespace(text=json.dumps({'succeeded': True, 'summary': 'Prepared test-only benchmark',
            'limitations': ['Provider operations are simulated'], 'output_files': list(package_files())}), files={})


def test_idea_to_public_dataset_and_research_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    donor, bootstrap = Donor(), Bootstrap()
    donor.start = bootstrap.start
    donor.check_benchmark_name = lambda arguments: {'status': 'available'}
    publications = []
    def publish(arguments):
        publications.append(arguments)
        return {'handle': 'verified-user/benchmark-' + arguments['run_id'],
                'url': 'https://www.kaggle.com/datasets/verified-user/benchmark-' + arguments['run_id'],
                'version': 1, 'visibility': 'public', 'manifest_sha256': arguments['manifest_sha256'],
                'files': arguments['files']}
    donor.publish_benchmark = publish
    runtime = BenchmarkRuntime(donor)
    @asynccontextmanager
    async def connection(config):
        yield donor
    config = SimpleNamespace(workspace_root=tmp_path, shutdown_seconds=1,
        kaggle_username='verified-user', kaggle_account_alias='fixture-account')
    app = create_app(config, bindings=SimpleNamespace(runtime=runtime, request_type=request_type), kaggle_connection=connection)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={'name': 'Inference benchmark'}).json()['id']
        base = '/api/projects/' + project
        assert client.post(base + '/ideas', json={'text': 'Benchmark', 'mode': 'benchmark'}).status_code == 422
        missing = client.post(base + '/ideas', json={'text': 'Improve cache'}).json()
        assert client.post(base + '/plan', json={'idea_id': missing['id']}).status_code == 409
        assert runtime.calls == [] and bootstrap.calls == []
        idea = client.post(base + '/ideas', json={'text': 'Create inference benchmark', 'mode': 'benchmark',
            'benchmark_definition': DEFINITION}).json()
        assert client.post(base + '/plan', json={'idea_id': idea['id']}).status_code == 202
        for _ in range(300):
            proposals = client.get(base + '/proposals').json()
            if proposals:
                break
            threading.Event().wait(.01)
        proposal = proposals[0]
        assert proposal['body']['split'] == {'test': DEFINITION['test_split'], 'train': None}
        run = client.post(base + '/proposals/' + proposal['id'] + '/approve', json={
            'version': proposal['version'], 'context_sha256': proposal['context_sha256']}).json()
        path = base + '/runs/' + run['id']
        assert client.post(path + '/working', json={}).status_code == 202
        for _ in range(400):
            detail = client.get(path).json()
            if detail['state'] in {'COMPLETED', 'FAILED'}:
                break
            threading.Event().wait(.01)
        assert detail['state'] == 'COMPLETED', detail
        assert detail['working']['stop_confirmed'] and detail['benchmark']['dataset']['visibility'] == 'public'
        assert len(publications) == 1 and len(bootstrap.calls) == 1
        benchmark = client.get(base + '/benchmarks').json()[0]
        research = client.post(base + '/ideas', json={'text': 'Reduce inference memory',
            'benchmark_id': benchmark['id']}).json()
        assert client.post(base + '/plan', json={'idea_id': research['id']}).status_code == 202
        for _ in range(300):
            candidates = client.get(base + '/proposals').json()
            if candidates[0]['idea_id'] == research['id']:
                break
            threading.Event().wait(.01)
        assert candidates[0]['body']['split']['train'] is None
        assert candidates[0]['context_snapshot']['idea']['benchmark'] == benchmark
        prompt = runtime.calls[-1].prompt
        assert 'train a model' in prompt and 'needs_clarification=true' in prompt


@pytest.mark.parametrize('private', [False, True])
@pytest.mark.parametrize('name_status', ['available', 'exists', 'unavailable'])
def test_kagglehub_publisher_forces_public_and_verifies_response(tmp_path, monkeypatch, private, name_status):
    from pathlib import Path
    from ai_scientist.workbench.store import canonical
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'kaggle mcp'))
    import benchmark_publish
    import account_store
    from kagglehub.gcs_upload import UploadDirectoryInfo
    from kagglesdk.datasets.types.dataset_enums import DatabundleVersionStatus
    files = []
    for name, data in package_files().items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    captured = []
    uploads = []
    def create(request):
        captured.append(request)
        return SimpleNamespace(error=None)
    def get_dataset(request):
        if not captured and name_status != 'exists':
            from requests import HTTPError, Response
            response = Response()
            response.status_code = 404 if name_status == 'available' else 403
            raise HTTPError('Fixture name lookup', response=response)
        return SimpleNamespace(ref='fixture/ais-benchmark-' + 'a'*32,
                               current_version_number=1, is_private=private)
    class Client:
        datasets = SimpleNamespace(dataset_api_client=SimpleNamespace(create_dataset=create,
            get_dataset=get_dataset,
            get_dataset_status=lambda request: SimpleNamespace(status=DatabundleVersionStatus.READY)))
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(account_store, 'resolve', lambda account: (account, {'username': 'fixture'}))
    monkeypatch.setattr(account_store, 'read_token', lambda account: 'fixture-token')
    monkeypatch.setenv('KAGGLE_API_TOKEN', '')
    monkeypatch.setattr('kagglehub.clients.build_kaggle_client', lambda: Client())
    def upload(*args, **kwargs):
        uploads.append(args)
        return UploadDirectoryInfo('benchmark', files=['token'])
    monkeypatch.setattr('kagglehub.gcs_upload.upload_files_and_directories', upload)
    arguments = {'directory': str(tmp_path / 'output/benchmark'), 'run_id': 'a'*32,
                 'title': 'Benchmark', 'files': files,
                 'manifest_sha256': hashlib.sha256(canonical(sorted(files, key=lambda item: item['path'])).encode()).hexdigest()}
    if name_status != 'available':
        with pytest.raises(ValueError, match='name gate'):
            benchmark_publish.publish('fixture', arguments)
        assert not captured and not uploads
        return
    if private:
        with pytest.raises(RuntimeError, match='Public'):
            benchmark_publish.publish('fixture', arguments)
    else:
        receipt = benchmark_publish.publish('fixture', arguments)
        assert receipt['visibility'] == 'public' and receipt['version'] == 1
        assert 'fixture-token' not in json.dumps(receipt)
    assert captured[0].is_private is False
    assert 6 <= len(captured[0].slug) <= 50 and 6 <= len(captured[0].title) <= 50


@pytest.mark.parametrize('overrides', [
    {'dataset_slug': ''},
    {'dataset_slug': 'a'*51}, {'dataset_slug': 'small'}, {'dataset_slug': 'Bad_Name'},
    {'dataset_slug': '-bad-name'}, {'dataset_slug': 'bad--name'}, {'dataset_slug': 'bad/name'},
    {'dataset_title': 'tiny'}, {'dataset_title': 'a'*51}, {'dataset_title': ' title-space '},
    {'dataset_title': 'bad\nname'},
])
def test_dataset_naming_gate_rejects_invalid_names(tmp_path, monkeypatch, overrides):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'kaggle mcp'))
    from benchmark_publish import dataset_name
    with pytest.raises(ValueError):
        dataset_name({'run_id': 'a'*32, 'title': 'Inference benchmark', **overrides})


def test_generated_dataset_title_truncation_does_not_leave_trailing_space(monkeypatch):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'kaggle mcp'))
    from benchmark_publish import dataset_name
    slug, title = dataset_name({'run_id':'a'*32, 'title':'a'*38 + ' more words'})
    assert slug == 'ais-benchmark-' + 'a'*32
    assert title == 'Benchmark: ' + 'a'*38


@pytest.mark.parametrize('case,expected', [('empty','available'),('collision','exists'),
    ('denied','unavailable'),('repeated','unavailable'),('foreign','unavailable'),('cursor','available')])
def test_absent_slug_403_requires_complete_authenticated_owner_listing(monkeypatch, case, expected):
    from pathlib import Path
    from requests import HTTPError, Response
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'kaggle mcp'))
    from benchmark_publish import _name_status
    from kagglesdk.datasets.types.dataset_enums import DatasetSelectionGroup
    calls=[]
    def denied(request):
        response=Response()
        response.status_code=403
        raise HTTPError('Fixture permission denied',response=response)
    def listing(request):
        calls.append((request.page,request.page_token))
        assert request.group == DatasetSelectionGroup.DATASET_SELECTION_GROUP_MY and request.user == 'fixture'
        if case == 'denied':
            return denied(request)
        refs = ['fixture/other']
        token = ''
        if case == 'foreign':
            refs = ['different/other']
        elif case == 'cursor':
            refs = ['fixture/other'] if len(calls)==1 else ['fixture/last']
            token = 'next-token' if len(calls)==1 else ''
        elif len(calls)>1:
            refs = ['fixture/target'] if case=='collision' else ['fixture/other'] if case=='repeated' else []
        return SimpleNamespace(datasets=[SimpleNamespace(ref=ref) for ref in refs], next_page_token=token)
    client=SimpleNamespace(datasets=SimpleNamespace(dataset_api_client=SimpleNamespace(
        get_dataset=denied,list_datasets=listing)))
    assert _name_status(client,'fixture','target') == expected
    assert calls and len(calls)<=2
    if case in {'empty','collision'}:
        assert calls == [(1,''),(2,'')]


def test_dataset_naming_gate_blocks_before_kaggle_session(tmp_path):
    donor, bootstrap = Donor(), Bootstrap()
    donor.start = bootstrap.start
    donor.check_benchmark_name = lambda arguments: {'status': 'exists', 'error': 'Tên dataset đã tồn tại.'}
    runtime = BenchmarkRuntime(donor)
    @asynccontextmanager
    async def connection(config):
        yield donor
    config = SimpleNamespace(workspace_root=tmp_path, shutdown_seconds=1,
        kaggle_username='verified-user', kaggle_account_alias='fixture-account')
    app = create_app(config, bindings=SimpleNamespace(runtime=runtime, request_type=request_type), kaggle_connection=connection)
    store = app.state.store
    project = store.create_project('Dataset name gate')['id']
    idea = store.save_idea(project, 'Inference benchmark', mode='benchmark', benchmark_definition=DEFINITION)
    run = approve(store, project, idea)
    with TestClient(app) as client:
        response = client.post(f'/api/projects/{project}/runs/{run["id"]}/working', json={})
        assert response.status_code == 409 and 'đã tồn tại' in response.json()['detail']
        assert not bootstrap.calls and not runtime.calls and not donor.opens
        assert app.state.working.record(project, run['id']) is None


def test_legacy_training_cannot_start_or_enter_batch_without_benchmark(tmp_path):
    store = ProjectStore(tmp_path / 'projects')
    project = store.create_project('Legacy unbound run')['id']
    idea = store.save_idea(project, 'Legacy training approval')
    run = approve(store, project, idea)
    app = FastAPI()
    app.include_router(library_router(store, tmp_path))
    # No Working service is mounted: the benchmark gate must reject before
    # provider submission or batch reservation is even reachable.
    with TestClient(app) as client:
        base = '/api/projects/' + project
        assert client.post(base + '/runs/' + run['id'] + '/working', json={}).status_code == 409
        assert client.post(base + '/runs/batch', json={'runs': [
            {'run_id': run['id'], 'account': account} for account in ('first', 'second')]}).status_code == 409
        assert store.run(project, run['id'])['state'] == 'APPROVED'


def test_mlflow_preflight_reports_tracking_failure_before_provider_calls(tmp_path, monkeypatch):
    monkeypatch.setenv('AI_SCIENTIST_MLFLOW_TRACKING_URI', 'unsupported-qa-store://no-fallback')
    donor, bootstrap = Donor(), Bootstrap()
    donor.start = bootstrap.start
    runtime = BenchmarkRuntime(donor)
    @asynccontextmanager
    async def connection(config):
        yield donor
    config = SimpleNamespace(workspace_root=tmp_path, shutdown_seconds=1,
        kaggle_username='verified-user', kaggle_account_alias='fixture-account')
    app = create_app(config, bindings=SimpleNamespace(runtime=runtime, request_type=request_type), kaggle_connection=connection)
    store = app.state.store
    project = store.create_project('MLflow preflight')['id']
    creator = store.save_idea(project, 'Prepare test', mode='benchmark', benchmark_definition=DEFINITION)
    benchmark_run = approve(store, project, creator)
    BenchmarkCatalog(store).save(project, benchmark_run['id'], 'Test benchmark', DEFINITION,
        {'handle': 'fixture/benchmark', 'url': 'https://www.kaggle.com/datasets/fixture/benchmark',
         'version': 1, 'visibility': 'public', 'manifest_sha256': 'a'*64, 'files': []})
    with store.connection(project) as connection:
        connection.execute("UPDATE runs SET state='COMPLETED' WHERE id=?", (benchmark_run['id'],))
    idea = store.save_idea(project, 'Improve inference', benchmark_id=benchmark_run['id'])
    run = approve(store, project, idea)
    with TestClient(app) as client:
        response = client.post(f'/api/projects/{project}/runs/{run["id"]}/working', json={})
        assert response.status_code == 503
        assert response.json()['detail'] == 'MLflow chưa sẵn sàng; chưa mở phiên Kaggle.'
        assert not bootstrap.calls and not runtime.calls and not donor.opens
        assert app.state.working.record(project, run['id']) is None
        assert store.run(project, run['id'])['state'] == 'APPROVED'
