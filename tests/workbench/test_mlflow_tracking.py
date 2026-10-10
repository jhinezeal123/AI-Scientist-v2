"""Merged PR regressions for required, immutable benchmark tracking."""
import pytest

from ai_scientist.workbench import benchmark_tracking
from ai_scientist.workbench.compare import _row
from benchmark_fixture import BENCHMARK
from test_compare import _working


def test_sync_to_mlflow_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.delenv('AI_SCIENTIST_MLFLOW_TRACKING_URI', raising=False)
    working = _working(tmp_path)
    client = benchmark_tracking.client_for(working)
    row = _row(working, 'project', 'a')
    experiment = benchmark_tracking.sync_rows(working, 'project', BENCHMARK, [row], client=client)
    identifier = row['mlflow_run_id']
    assert len(client.get_metric_history(identifier, 'EMD')) == 2
    assert client.get_run(identifier).data.params['budget.steps'] == '10'

    again = _row(working, 'project', 'a')
    assert benchmark_tracking.sync_rows(working, 'project', BENCHMARK, [again], client=client) == experiment
    assert again['mlflow_run_id'] == identifier
    assert len(client.search_runs([experiment])) == 1
    assert len(client.get_metric_history(identifier, 'EMD')) == 2


def test_reject_benchmark_and_metric_provenance_changes(tmp_path, monkeypatch):
    monkeypatch.delenv('AI_SCIENTIST_MLFLOW_TRACKING_URI', raising=False)
    working = _working(tmp_path)
    client = benchmark_tracking.client_for(working)
    row = _row(working, 'project', 'a')
    benchmark_tracking.sync_rows(working, 'project', BENCHMARK, [row], client=client)
    identifier = row['mlflow_run_id']
    fingerprint = client.get_run(identifier).data.tags['benchmark_sha256']
    client.set_tag(identifier, 'benchmark_sha256', '0' * 64)
    with pytest.raises(ValueError, match='provenance'):
        benchmark_tracking.sync_rows(working, 'project', BENCHMARK, [_row(working, 'project', 'a')], client=client)
    client.set_tag(identifier, 'benchmark_sha256', fingerprint)

    changed = _row(working, 'project', 'a')
    changed['points'][-1]['metrics']['EMD'] = .9
    with pytest.raises(ValueError, match='verified final measurement'):
        benchmark_tracking.sync_rows(working, 'project', BENCHMARK, [changed], client=client)


def test_tracking_outage_blocks_preflight_without_fallback(tmp_path, monkeypatch):
    def unavailable(*args):
        raise ConnectionError('offline')
    monkeypatch.setattr(benchmark_tracking, 'client_for', unavailable)
    with pytest.raises(benchmark_tracking.TrackingUnavailable, match='MLflow'):
        benchmark_tracking.ensure_tracking(_working(tmp_path), 'project', BENCHMARK)
