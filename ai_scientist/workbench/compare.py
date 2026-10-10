"""Compare MLflow measurements for runs using the same frozen benchmark."""
import math

from .benchmarks import BenchmarkCatalog, approval_benchmark
from .benchmark_tracking import sync_rows
from .store import canonical


def _row(working, project_id, run_id):
    detail = working.detail(project_id, run_id)
    approved = working.store.approved_snapshot(project_id, run_id)
    benchmark = approval_benchmark(approved['snapshot'])
    record = working.record(project_id, run_id)
    return {
        'run_id': run_id, 'title': detail['title'], 'purpose': detail['purpose'],
        'state': detail['state'], 'account': detail.get('account'),
        'parent_run_id': (detail.get('variant') or {}).get('parent_run_id') or detail.get('parent_run_id'),
        'metric': detail.get('result_metric'), 'benchmark': benchmark,
        'budget': approved['body'].get('budget') or {},
        'protocol': {'mode': detail['mode'], 'benchmark_id': benchmark['id'] if benchmark else None,
                     'metric': benchmark['definition']['metric'] if benchmark else None},
        'points': working.records.logs(project_id, run_id, limit=1)['points'] if record else [],
    }


def sync_run(working, project_id, run_id):
    row = _row(working, project_id, run_id)
    if not row['benchmark']:
        raise ValueError('Run has no frozen benchmark')
    experiment = sync_rows(working, project_id, row['benchmark'], [row])
    return {'experiment_id': experiment, 'mlflow_run_id': row['mlflow_run_id']}


def _compare(working, project_id, run_ids, benchmark=None):
    rows = [_row(working, project_id, run_id) for run_id in run_ids]
    same = bool(benchmark or rows) and all(row['protocol']['mode'] == 'training_research' and row['benchmark'] for row in rows)
    references = {canonical(row['benchmark']) for row in rows}
    same = same and len(references) <= 1
    if benchmark:
        same = same and all(row['benchmark'] == benchmark for row in rows)
    warnings = []
    experiment = None
    if not same:
        warnings.append('Chỉ so sánh chung các run có cùng benchmark và phiên bản dataset đã đóng băng.')
        for row in rows:
            row['metric'], row['points'] = None, []
    elif rows:
        benchmark = benchmark or rows[0]['benchmark']
        try:
            experiment = sync_rows(working, project_id, benchmark, rows)
        except Exception as exc:
            raise RuntimeError('MLflow chưa đồng bộ hoặc không xác minh được dữ liệu. Không có fallback; thử đồng bộ lại.') from exc
    ranked = []
    if same and rows:
        metrics = [row['metric'] for row in rows]
        if all(row['state'] == 'COMPLETED' and metric and type(metric.get('final_value')) in (int, float)
               and math.isfinite(metric['final_value']) for row, metric in zip(rows, metrics)):
            ranked = [row['run_id'] for row in sorted(rows, key=lambda row: row['metric']['final_value'],
                      reverse=benchmark['definition']['metric']['direction'] == 'maximize')]
        else:
            warnings.append('Đang hiển thị các mẫu đo MLflow; xếp hạng cuối khi mọi run hoàn tất và có metric hợp lệ.')
    return {'runs': rows, 'same_protocol': bool(same), 'benchmark': benchmark,
            'warnings': warnings, 'ranked_run_ids': ranked, 'tracking_backend': 'mlflow',
            'experiment_id': experiment}


def compare_runs(working, project_id, run_ids):
    if not 2 <= len(run_ids) <= 8 or len(set(run_ids)) != len(run_ids):
        raise ValueError('Choose 2–8 distinct runs to compare')
    return _compare(working, project_id, run_ids)


def compare_benchmark(working, project_id, benchmark_id):
    benchmark = BenchmarkCatalog(working.store).require(project_id, benchmark_id)
    ids = [row['id'] for row in working.store.history(project_id)['runs']
           if approval_benchmark(working.store.approved_snapshot(project_id, row['id'])['snapshot']) == benchmark]
    return _compare(working, project_id, ids, benchmark)