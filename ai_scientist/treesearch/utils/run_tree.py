"""A single run tree built from saved journals, without evaluation or agent calls."""
from copy import deepcopy
import json
from pathlib import Path
import re

from .metric import MetricValue
from .tree_export import format_metric, generate_layout, normalize_layout


def _stage_number(name):
    match = re.match(r'(?:stage_)?([1-4])_', name)
    if not match:
        raise ValueError('Invalid journal stage name')
    return int(match[1])


def build_run_tree(journals, *, title='', status=None, selected_node_id=None):
    """Deduplicate inherited baselines while preserving their original ancestry."""
    records, origins = {}, {}
    ordered = sorted(journals, key=lambda name: (_stage_number(name), name))
    for stage_name in ordered:
        for record in journals[stage_name]['nodes']:
            node_id = record['id']
            if node_id not in records:
                records[node_id] = deepcopy(record)
                origins[node_id] = stage_name
            else:
                # Inherited baselines have the same ID but can lose their parent
                # in the next journal. Keep the original edge, never that reset.
                parent = record.get('parent_id')
                previous = records[node_id].get('parent_id')
                if parent and previous and parent != previous:
                    raise ValueError('Conflicting journal node parents')
                if parent and not previous:
                    records[node_id]['parent_id'] = parent

    ids = list(records)
    indices = {node_id: index for index, node_id in enumerate(ids)}
    edges, depths, warnings = [], {}, []
    for node_id, record in records.items():
        parent = record.get('parent_id')
        if parent in indices:
            edges.append([indices[parent], indices[node_id]])
        elif parent:
            warnings.append(f'Không có node cha {parent} của node {node_id} trong journal đã lưu.')
        seen, ancestor, depth = {node_id}, parent, 0
        while ancestor in records:
            if ancestor in seen:
                raise ValueError('Journal parent cycle')
            seen.add(ancestor)
            depth += 1
            ancestor = records[ancestor].get('parent_id')
        depths[node_id] = depth

    layout = normalize_layout(generate_layout(len(ids), edges)).tolist() if ids else []
    nodes = []
    for index, node_id in enumerate(ids):
        record = records[node_id]
        parent = record.get('parent_id')
        parent_record = records.get(parent)
        metric = record.get('metric')
        nodes.append({
            'id': node_id, 'index': index, 'parent_id': parent,
            'stage': _stage_number(origins[node_id]), 'stage_name': origins[node_id],
            'action': 'draft' if not parent else 'debug' if parent_record and parent_record.get('is_buggy') else 'improve',
            'is_buggy': record.get('is_buggy'),
            'plan': record.get('plan'), 'code': record.get('code'),
            'analysis': record.get('analysis'), 'term_out': record.get('_term_out'),
            'metric': format_metric(MetricValue.from_dict(metric)) if metric else None,
            'exec_time': record.get('exec_time'), 'exc_type': record.get('exc_type'),
            'exc_info': record.get('exc_info'), 'exc_stack': record.get('exc_stack'),
            'feedback': record.get('vlm_feedback_summary'),
            'datasets': record.get('datasets_successfully_tested'),
            'plots': record.get('plots'), 'plot_plan': record.get('plot_plan'),
            'plot_code': record.get('plot_code'), 'plot_analyses': record.get('plot_analyses'),
            'exec_time_feedback': record.get('exec_time_feedback'),
        })
    return {'title': title, 'status': status, 'nodes': nodes, 'edges': edges,
            'layout': layout, 'depth': max(depths.values(), default=0),
            'selected_node_id': selected_node_id, 'warnings': warnings}


def render_run_tree(data):
    templates = Path(__file__).parent / 'viz_templates'
    script = (templates / 'run_tree.js').read_text(encoding='utf-8')
    # Journal content is untrusted. Keep it inside JSON and render text via DOM.
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    script = script.replace('"PLACEHOLDER_TREE_DATA"', encoded)
    return (templates / 'run_tree.html').read_text(encoding='utf-8').replace('<!-- placeholder -->', script)


def render_search_state(state, title=''):
    return render_run_tree(build_run_tree(state['journals'], title=title,
        status=state.get('status'), selected_node_id=state.get('selected_node_id')))
