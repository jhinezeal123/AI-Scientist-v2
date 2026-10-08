"""Single-tree ancestry and saved-run rendering; no agent or Kaggle calls."""
from copy import deepcopy
import json

from fastapi.testclient import TestClient
import pytest

from ai_scientist.treesearch.journal import Node
from ai_scientist.treesearch.utils.metric import MetricValue
from ai_scientist.treesearch.utils.run_tree import build_run_tree, render_search_state
from ai_scientist.workbench.experiments import prepare_experiment
from test_implementation import approved_run
from test_planning import FakeRuntime
from test_session_recovery import application
from test_working import MCP


def saved_tree():
    draft = Node(id='a'*32, plan='draft', code='print(1)', is_buggy=True)
    debug = Node(id='b'*32, parent=draft, plan='debug', is_buggy=False, metric=MetricValue(0.5, maximize=True))
    tuning = Node(id='c'*32, parent=debug, plan='tuning', is_buggy=False)
    branch = Node(id='d'*32, parent=debug, plan='alternative', is_buggy=False)
    research = Node(id='e'*32, parent=tuning, plan='research', is_buggy=False)
    ablation = Node(id='f'*32, parent=research, plan='ablation', is_buggy=False)
    journals = {}
    for stage, nodes in enumerate(((draft,debug), (debug,tuning,branch), (tuning,research), (research,ablation)), 1):
        records = [node.to_dict() for node in nodes]
        if stage > 1:
            records[0]['parent_id'] = None  # Upstream stage baseline copy.
        journals[f'{stage}_stage_1_first'] = {'nodes': records}
    return {'journals': journals, 'status': 'completed', 'options': {},
            'stages': [], 'selected_node_id': ablation.id}


def test_run_tree_deduplicates_baselines_preserves_cross_stage_and_branch_edges(monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError('Rendering must not call an agent')
    monkeypatch.setattr('ai_scientist.treesearch.journal.query', forbidden)
    saved = saved_tree()
    before = deepcopy(saved)
    tree = build_run_tree(saved['journals'])
    assert saved == before
    assert [node['stage'] for node in tree['nodes']] == [1,1,2,2,3,4]
    assert tree['edges'] == [[0,1],[1,2],[1,3],[2,4],[4,5]]
    assert tree['nodes'][1]['action'] == 'debug'
    assert tree['nodes'][1]['metric']['metric_names'][0]['data'][0]['final_value'] == 0.5
    assert len(tree['layout']) == 6 and not tree['warnings']


@pytest.mark.parametrize('count', [0, 1])
def test_empty_or_single_node_tree_is_visible_without_edges(count):
    journals = {'1_stage_1_first': {'nodes': [Node(id='a'*32).to_dict()] if count else []}}
    tree = build_run_tree(journals)
    assert len(tree['nodes']) == len(tree['layout']) == count
    assert tree['edges'] == []


def test_run_tree_rejects_cycles_and_escapes_untrusted_content():
    state = saved_tree()
    state['journals']['1_stage_1_first']['nodes'][0]['code'] = '</script><img src=x onerror=alert(1)>'
    html = render_search_state(state)
    assert '</script><img' not in html and '\\u003c/script>' in html
    assert 'stage-tabs' not in html and 'p5.min.js' not in html
    state['journals']['1_stage_1_first']['nodes'][0]['parent_id'] = 'b'*32
    with pytest.raises(ValueError, match='cycle'):
        build_run_tree(state['journals'])


def test_saved_run_url_uses_current_view_without_mutating_artifacts(tmp_path, monkeypatch):
    runtime, mcp = FakeRuntime(), MCP()
    app = application(tmp_path, runtime, mcp, monkeypatch)
    store = app.state.store
    project, run = approved_run(store)
    root = prepare_experiment(store, tmp_path, project, run['id'], store.approved_snapshot(project, run['id']))
    logs = root / 'logs/0-run'
    (logs/'search-state.json').write_text(json.dumps(saved_tree()), encoding='utf-8')
    (logs/'unified_tree_viz.html').write_text('historical viewer', encoding='utf-8')
    before = {path.name: path.read_bytes() for path in logs.iterdir() if path.is_file()}
    with TestClient(app) as client:
        path = f'/api/projects/{project}/runs/{run["id"]}/artifacts/logs/0-run/unified_tree_viz.html'
        response = client.get(path)
        assert response.status_code == 200
        assert 'Các bản thử' in response.text and 'node-detail' in response.text
        assert 'sandbox allow-scripts' in response.headers['content-security-policy']
        assert client.head(path).status_code == 200
        other = store.create_project('Other')['id']
        assert client.get(path.replace(project, other)).status_code == 404
    assert before == {path.name: path.read_bytes() for path in logs.iterdir() if path.is_file()}
    assert not runtime.calls and not mcp.calls
