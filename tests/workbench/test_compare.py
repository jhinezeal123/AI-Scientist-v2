"""Benchmark comparisons against a real local MLflow SQLite backend."""
import copy
from types import SimpleNamespace

import pytest

from ai_scientist.workbench.compare import compare_runs, compare_benchmark
from ai_scientist.workbench.benchmark_tracking import client_for
from benchmark_fixture import BENCHMARK


def _working(tmp_path, benchmark_b=None):
    class Store:
        root = tmp_path / 'projects'
        def approved_snapshot(self, project, run):
            benchmark = benchmark_b if run == 'b' and benchmark_b else BENCHMARK
            return {'body': {'budget': {'steps': 10 if run == 'a' else 100}},
                    'snapshot': {'idea': {'benchmark': benchmark}}}
    class Working:
        store = Store()
        def detail(self, project, run):
            return {'title': run, 'purpose': run, 'state': 'COMPLETED', 'account': run,
                    'mode': 'training_research', 'variant': None, 'parent_run_id': None,
                    'result_metric': {'name': 'EMD', 'direction': 'minimize',
                                      'final_value': 0.1 if run == 'a' else 0.2}}
        def record(self, project, run):
            return {'stop_confirmed': True}
    def logs(project, run, limit=1):
        total, final = (10, .1) if run == 'a' else (100, .2)
        return {'points': [{'step': step, 'total_steps': total, 'elapsed_seconds': step,
                          'metrics': {'EMD': value}} for step, value in [(1, .9), (total, final)]]}
    working = Working()
    working.records = SimpleNamespace(logs=logs)
    return working


def test_rank_same_benchmark_even_with_10_and_100_steps(tmp_path, monkeypatch):
    monkeypatch.delenv('AI_SCIENTIST_MLFLOW_TRACKING_URI', raising=False)
    working = _working(tmp_path)
    result = compare_runs(working, 'project', ['a', 'b'])
    assert result['same_protocol'] and result['ranked_run_ids'] == ['a', 'b']
    assert result['tracking_backend'] == 'mlflow'
    assert [row['points'][-1]['step'] for row in result['runs']] == [10, 100]
    client = client_for(working)
    for row in result['runs']:
        assert client.get_run(row['mlflow_run_id']).info.status == 'FINISHED'
    again = compare_runs(working, 'project', ['a', 'b'])
    assert [r['mlflow_run_id'] for r in again['runs']] == [r['mlflow_run_id'] for r in result['runs']]
    assert len(client.get_metric_history(result['runs'][0]['mlflow_run_id'], 'EMD')) == 2


def test_different_benchmark_version_never_compares(tmp_path, monkeypatch):
    changed = copy.deepcopy(BENCHMARK)
    changed['dataset']['version'] = 2
    monkeypatch.setattr('ai_scientist.workbench.compare.sync_rows', lambda *a: pytest.fail('Do not sync incompatible groups'))
    result = compare_runs(_working(tmp_path, changed), 'project', ['a', 'b'])
    assert not result['same_protocol'] and not result['ranked_run_ids']
    assert all(row['metric'] is None and row['points'] == [] for row in result['runs'])


def test_mlflow_failure_has_no_workbench_fallback(tmp_path, monkeypatch):
    def unavailable(*args):
        raise ConnectionError('MLflow unavailable')
    monkeypatch.setattr('ai_scientist.workbench.compare.sync_rows', unavailable)
    with pytest.raises(RuntimeError, match='MLflow'):
        compare_runs(_working(tmp_path), 'project', ['a', 'b'])


def test_unverified_extra_step_blocks_comparison(tmp_path, monkeypatch):
    monkeypatch.delenv('AI_SCIENTIST_MLFLOW_TRACKING_URI', raising=False)
    working = _working(tmp_path)
    result = compare_runs(working, 'project', ['a', 'b'])
    client = client_for(working)
    client.log_metric(result['runs'][0]['mlflow_run_id'], 'EMD', .1, step=999)
    with pytest.raises(RuntimeError, match='MLflow'):
        compare_runs(working, 'project', ['a', 'b'])


def test_wrong_or_missing_final_metric_blocks_comparison(tmp_path, monkeypatch):
    monkeypatch.delenv('AI_SCIENTIST_MLFLOW_TRACKING_URI', raising=False)
    working = _working(tmp_path)
    detail = working.detail
    working.detail = lambda project, run: {**detail(project, run), 'result_metric': None}
    with pytest.raises(RuntimeError, match='MLflow'):
        compare_runs(working, 'project', ['a', 'b'])


def test_partial_import_repairs_params_on_retry(tmp_path, monkeypatch):
    from ai_scientist.workbench.benchmark_tracking import sync_rows
    from ai_scientist.workbench.compare import _row
    monkeypatch.delenv('AI_SCIENTIST_MLFLOW_TRACKING_URI', raising=False)
    working = _working(tmp_path)
    client = client_for(working)
    original = client.log_batch
    def lost(*args, **kwargs):
        raise ConnectionError('Connection lost after create_run')
    client.log_batch = lost
    with pytest.raises(ConnectionError):
        sync_rows(working, 'project', BENCHMARK, [_row(working, 'project', 'a')], client=client)
    client.log_batch = original
    row = _row(working, 'project', 'a')
    sync_rows(working, 'project', BENCHMARK, [row], client=client)
    params = client.get_run(row['mlflow_run_id']).data.params
    assert params['budget.steps'] == '10' and params['benchmark.dataset_version'] == '1'


def test_benchmark_chart_contains_all_runs_without_manual_selection_limit(tmp_path, monkeypatch):
    monkeypatch.delenv('AI_SCIENTIST_MLFLOW_TRACKING_URI', raising=False)
    working = _working(tmp_path)
    ids = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i']
    working.store.history = lambda project: {'runs': [{'id': run} for run in ids]}
    monkeypatch.setattr('ai_scientist.workbench.benchmarks.BenchmarkCatalog.require',
                        lambda *args: BENCHMARK)
    result = compare_benchmark(working, 'project', BENCHMARK['id'])
    assert [row['run_id'] for row in result['runs']] == ids
    assert len(result['ranked_run_ids']) == 9 and result['same_protocol']
    assert all(row['mlflow_run_id'] for row in result['runs'])
