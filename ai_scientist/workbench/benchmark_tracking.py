"""Required MLflow storage, grouped by the immutable benchmark reference."""
import hashlib
import math
import os
import re
from pathlib import Path
import threading
import time

from .store import canonical

_LOCK = threading.RLock()


class TrackingUnavailable(RuntimeError):
    """Safe public error for the mandatory tracking preflight."""


def client_for(working):
    from mlflow.tracking import MlflowClient
    directory = working.store.root.parent / 'mlflow'
    directory.mkdir(parents=True, exist_ok=True)
    uri = os.environ.get('AI_SCIENTIST_MLFLOW_TRACKING_URI', '').strip()
    return MlflowClient(tracking_uri=uri or 'sqlite:///' + (directory / 'mlflow.db').resolve().as_posix())


def experiment_for(client, working, project_id, benchmark):
    name = f"AI-Scientist/{project_id}/benchmarks/{benchmark['id']}"
    experiment = client.get_experiment_by_name(name)
    if experiment:
        return experiment.experiment_id
    directory = working.store.root.parent / 'mlflow/artifacts' / project_id / benchmark['id']
    directory.mkdir(parents=True, exist_ok=True)
    try:
        return client.create_experiment(name, artifact_location=directory.resolve().as_uri())
    except Exception:
        experiment = client.get_experiment_by_name(name)
        if experiment is None:
            raise
        return experiment.experiment_id


def ensure_tracking(working, project_id, benchmark):
    try:
        client = client_for(working)
        return experiment_for(client, working, project_id, benchmark)
    except Exception as exc:
        raise TrackingUnavailable('MLflow chưa sẵn sàng; chưa mở phiên Kaggle.') from exc


def sync_rows(working, project_id, benchmark, rows, *, client=None):
    """Import measured telemetry, verify persisted history, and never fall back."""
    from mlflow.entities import Metric, Param, RunTag
    with _LOCK:
        client = client or client_for(working)
        experiment = experiment_for(client, working, project_id, benchmark)
        fingerprint = hashlib.sha256(canonical(benchmark).encode()).hexdigest()
        spec = benchmark['definition']['metric']
        updates = []
        for row in rows:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', row['run_id']):
                raise ValueError('Unsafe run ID')
            found = client.search_runs([experiment], filter_string=f"tags.workbench_run_id = '{row['run_id']}'", max_results=2)
            if len(found) > 1:
                raise ValueError('Duplicate MLflow mapping')
            run = found[0] if found else client.create_run(experiment, run_name=row['title'][:250], tags={
                'workbench_run_id': row['run_id'], 'workbench_project_id': project_id,
                'benchmark_id': benchmark['id'], 'benchmark_sha256': fingerprint,
                'benchmark_dataset': benchmark['dataset']['handle'],
                'benchmark_dataset_version': str(benchmark['dataset']['version']),
            })
            if (run.data.tags.get('benchmark_sha256') != fingerprint
                    or run.data.tags.get('workbench_project_id') != project_id):
                raise ValueError('MLflow benchmark provenance mismatch')
            name = spec['name']
            desired = {}
            for point in row['points']:
                step, value = point.get('step'), point.get('metrics', {}).get(name)
                if type(step) is not int or step < 0 or type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError('Invalid measured benchmark history')
                if step in desired:
                    raise ValueError('Duplicate measured step')
                desired[step] = float(value)
            verified = row.get('metric')
            if row['state'] == 'COMPLETED':
                if (not verified or verified.get('name') != name or verified.get('direction') != spec['direction']
                        or not desired or desired[max(desired)] != verified.get('final_value')):
                    raise ValueError('Completed benchmark run lacks a verified final measurement')
            history = client.get_metric_history(run.info.run_id, name)
            existing = {}
            for point in history:
                if point.step in existing and existing[point.step] != point.value:
                    raise ValueError('Conflicting MLflow history')
                existing[point.step] = point.value
            if any(step not in desired or desired[step] != value for step, value in existing.items()):
                raise ValueError('MLflow contains unverified steps or values')
            params = {'benchmark.definition_sha256': hashlib.sha256(canonical(benchmark['definition']).encode()).hexdigest(),
                      'benchmark.dataset_version': str(benchmark['dataset']['version'])}
            params.update({f'budget.{key}': str(value) for key, value in row.get('budget', {}).items()})
            for key, value in params.items():
                if key in run.data.params and run.data.params[key] != value:
                    raise ValueError('MLflow parameter mismatch')
            client.log_batch(run.info.run_id,
                metrics=[Metric(name, value, int(time.time() * 1000), step) for step, value in desired.items() if step not in existing],
                params=[Param(key, value) for key, value in params.items() if key not in run.data.params],
                tags=[RunTag('workbench_state', row['state']), RunTag('metric_direction', spec['direction']),
                      RunTag('account', row.get('account') or ''), RunTag('parent_run_id', row.get('parent_run_id') or '')])
            status = {'COMPLETED': 'FINISHED', 'FAILED': 'FAILED', 'CANCELLED': 'KILLED'}.get(row['state'])
            if status:
                client.set_terminated(run.info.run_id, status=status)
            persisted = client.get_run(run.info.run_id)
            actual = {}
            for point in client.get_metric_history(run.info.run_id, name):
                if point.step in actual and actual[point.step] != point.value:
                    raise ValueError('Conflicting MLflow history after sync')
                actual[point.step] = point.value
            if actual != desired or any(persisted.data.params.get(key) != value for key, value in params.items()):
                raise ValueError('MLflow persistence verification failed')
            if verified and persisted.data.metrics.get(name) != verified.get('final_value'):
                raise ValueError('MLflow final metric differs from the verified result')
            points = [{**point, 'metrics': {name: actual[point['step']]}} for point in row['points']]
            updates.append((row, persisted, points))
        for row, run, points in updates:
            row['mlflow_run_id'] = run.info.run_id
            row['points'] = points
            if row.get('metric'):
                row['metric'] = {**row['metric'], 'final_value': run.data.metrics[spec['name']]}
        return experiment
