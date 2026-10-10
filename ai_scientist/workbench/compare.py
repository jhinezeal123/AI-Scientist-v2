"""Compare saved run results only when approved evaluation protocols match."""
import math

from .store import canonical


def compare_runs(working, project_id, run_ids):
    if not 2 <= len(run_ids) <= 8 or len(set(run_ids)) != len(run_ids):
        raise ValueError('Choose 2–8 distinct runs to compare')
    rows = []
    for run_id in run_ids:
        detail = working.detail(project_id, run_id)
        approved = working.store.approved_snapshot(project_id, run_id)
        body, snapshot = approved['body'], approved['snapshot']
        selected = set(body.get('data_refs') or [])
        sources = sorted((resource['id'], resource['version'], resource['content_sha256'])
                         for resource in snapshot['resources'] if resource['id'] in selected)
        protocol = {'mode': detail['mode'], 'data': sources, 'split': body.get('split'),
                    'metric': body.get('metric')}
        metric = detail.get('result_metric')
        rows.append({'run_id': run_id, 'title': detail['title'], 'purpose': detail['purpose'],
                     'state': detail['state'], 'account': detail.get('account'),
                     'parent_run_id': (detail.get('variant') or {}).get('parent_run_id') or detail.get('parent_run_id'),
                     'metric': metric, 'protocol': protocol})
        record = working.record(project_id, run_id) if hasattr(working, 'record') else None
        rows[-1]['points'] = working.records.logs(project_id, run_id, limit=1)['points'] if record else []
    warnings = []
    if any(row['protocol']['mode'] != 'training_research' for row in rows):
        warnings.append('Run Etc không có protocol training để xếp hạng metric chung.')
    for field, label in [('data', 'nguồn dữ liệu'), ('split', 'split'), ('metric', 'metric')]:
        if any(not row['protocol'][field] for row in rows):
            warnings.append(f'Thiếu {label} trong protocol đã duyệt; chưa thể xác nhận cùng phép đo.')
        if len({canonical(row['protocol'][field]) for row in rows}) > 1:
            warnings.append(f'Khác {label} đã duyệt; không xếp hạng chung.')
    comparable = not warnings
    metrics = [row['metric'] for row in rows]
    if comparable and (any(row['state'] != 'COMPLETED' or not metric
                           or not isinstance(row['protocol']['metric'], dict)
                           or metric.get('name') != row['protocol']['metric'].get('name')
                           or metric.get('direction') != row['protocol']['metric'].get('direction')
                           or metric.get('direction') not in {'maximize', 'minimize'}
                           or type(metric.get('final_value')) not in (int, float)
                           or not math.isfinite(metric['final_value']) for row, metric in zip(rows, metrics))
                       or len({(metric.get('name'), metric.get('direction')) for metric in metrics}) != 1):
        warnings.append('Chưa có metric cuối hợp lệ cho mọi run; chưa thể xếp hạng.')
    ranked = []
    if not warnings:
        reverse = metrics[0]['direction'] == 'maximize'
        ranked = [row['run_id'] for row in sorted(rows, key=lambda row: row['metric']['final_value'], reverse=reverse)]
    return {'runs': rows, 'same_protocol': comparable, 'warnings': warnings, 'ranked_run_ids': ranked}
