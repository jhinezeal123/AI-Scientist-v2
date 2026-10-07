from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from ai_scientist.workbench.api import library_router
from ai_scientist.workbench.log_window import read_log_window
from ai_scientist.workbench.monitor_store import MonitorStore
from ai_scientist.workbench.store import ProjectStore
from ai_scientist.workbench.working_store import WorkingStore
from test_implementation import approved_run


@pytest.fixture
def fixture(tmp_path):
    store = ProjectStore(tmp_path / 'projects')
    project, run = approved_run(store)
    return store, project, run['id']


def insert(store, project, run, texts, generation=1):
    with store.connection(project) as connection:
        connection.executemany('INSERT INTO logs(run_id,generation,seq,text,stream) VALUES(?,?,?,?,?)',
            [(run, generation, seq, text, 'stderr' if seq == 2 else 'stdout')
             for seq, text in enumerate(texts, 1)])


def test_empty_and_metadata_only(fixture):
    store, project, run = fixture
    empty = read_log_window(store, project, run, 1)
    assert empty['total_lines'] == empty['total_records'] == 0 and empty['lines'] == []
    insert(store, project, run, ['first\nsecond\n', 'third'])
    metadata = read_log_window(store, project, run, 1, limit=0)
    assert metadata['total_records'] == 2 and metadata['total_lines'] == 3
    assert metadata['lines'] == [] and 'text' not in metadata


def test_display_lines_across_record_boundaries(fixture):
    store, project, run = fixture
    insert(store, project, run, ['A\r\nB\n', '\n', '', 'C\n\nD', 'E'])
    expected = ['A', 'B', '', '', 'C', '', 'D', 'E']
    all_lines = []
    for offset in range(0, len(expected), 3):
        page = read_log_window(store, project, run, 1, offset, 3)
        assert len(page['lines']) <= 3 and page['total_lines'] == len(expected)
        all_lines.extend(page['lines'])
    assert [line['text'] for line in all_lines] == expected
    assert [line['index'] for line in all_lines] == list(range(len(expected)))
    assert all_lines[2]['seq'] == 2 and all_lines[2]['stream'] == 'stderr'
    assert read_log_window(store, project, run, 1, 999)['lines'] == []


def test_jump_to_tail_is_bounded_and_preserves_history(fixture):
    store, project, run = fixture
    insert(store, project, run, ['\n'.join(str(index) for index in range(2000)) + '\n'])
    page = read_log_window(store, project, run, 1, 1960, 80)
    assert page['total_lines'] == 2000 and len(page['lines']) == 40
    assert page['lines'][0]['text'] == '1960' and page['lines'][-1]['text'] == '1999'
    assert len(read_log_window(store, project, run, 1, 0, 200)['lines']) == 200
    with store.connection(project) as connection:
        assert connection.execute('SELECT COUNT(*) FROM logs WHERE run_id=?', (run,)).fetchone()[0] == 1


def test_generation_reset_never_mixes_old_lines(fixture):
    store, project, run = fixture
    insert(store, project, run, ['old'])
    insert(store, project, run, ['new\nnext'], generation=2)
    page = read_log_window(store, project, run, 2, 900, 80, requested_generation=1)
    assert page['reset'] and page['offset'] == 0 and page['total_records'] == 1
    assert [line['text'] for line in page['lines']] == ['new', 'next']


def test_live_append_refreshes_a_partial_window(fixture):
    store, project, run = fixture
    records = WorkingStore(store)
    records.reserve(project, run, 'cpu', 600)
    records.append_log(project, run, 'A\n')
    assert len(read_log_window(store, project, run, 1, limit=80)['lines']) == 1
    records.append_log(project, run, 'B\nC\n')
    refreshed = read_log_window(store, project, run, 1, limit=80)
    assert [line['text'] for line in refreshed['lines']] == ['A', 'B', 'C']
    assert refreshed['total_lines'] == 3


@pytest.mark.parametrize('kwargs', [{'offset': -1}, {'limit': -1}, {'limit': 201}, {'requested_generation': 0}])
def test_invalid_window(fixture, kwargs):
    store, project, run = fixture
    with pytest.raises(ValueError):
        read_log_window(store, project, run, 1, **kwargs)


@pytest.mark.parametrize('modern', [False, True])
def test_http_window_and_existing_cursor_api(fixture, modern):
    store, project, run = fixture
    records = WorkingStore(store)
    monitor = MonitorStore(store)
    if modern:
        records.reserve(project, run, 'cpu', 600)
        records.append_log(project, run, 'A\nB\n')
        records.append_log(project, run, 'C\n', 'stderr')
    else:
        monitor.merge(project, run, {'records': [{'data': 'A\nB\n', 'stream_name': 'stdout', 'time': 1},
            {'data': 'C\n', 'stream_name': 'stderr', 'time': 2}], 'complete': False, 'terminal': False,
            'identity': {'status': 'RUNNING'}, 'observed_at': 'fixture', 'source': 'fixture'}, 'score', 'minimize')
    app = FastAPI()
    app.state.working = SimpleNamespace(record=records.get, records=records)
    app.state.logs = monitor
    app.include_router(library_router(store, store.root))
    base = f'/api/projects/{project}/runs/{run}'
    with TestClient(app) as client:
        metadata = client.get(base + '/log-window?limit=0').json()
        assert metadata['total_records'] == 2 and metadata['total_lines'] == 3
        assert metadata['entries'] == metadata['lines'] == []
        page = client.get(base + '/log-window?offset=1&limit=1').json()
        assert [line['text'] for line in page['lines']] == ['B'] and page['generation'] == 1
        old = client.get(base + '/logs?limit=1').json()
        assert old['entries'][0]['text'] == 'A\nB\n' and old['has_more']
        assert client.get(base + '/log-window?limit=201').status_code == 422
        assert client.get(base + '/log-window?offset=-1').status_code == 422
        other = store.create_project('Other')['id']
        assert client.get(f'/api/projects/{other}/runs/{run}/log-window').status_code == 404
