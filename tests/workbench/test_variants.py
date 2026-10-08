import hashlib
import json

import pytest

from ai_scientist.workbench.run_view import RunView
from ai_scientist.workbench.store import ProjectStore, StoreConflict
from ai_scientist.workbench.working_store import SCHEMA as WORKING_SCHEMA, WorkingStore
from test_implementation import approved_run
from test_planning import ready


def test_variant_request_ownership_stop_gate_and_pinned_hash(tmp_path):
    store = ProjectStore(tmp_path / '.workbench/projects')
    project, run = approved_run(store)
    other_project = store.create_project('other')['id']
    view = RunView(store, tmp_path, lambda: False)
    root = view.root(project, run['id'])
    (root / 'source').mkdir(parents=True)
    code = b"print('saved parent code')\n"
    generated_source = b"def make_features(rows):\n    return rows\n"
    report = b'# Saved parent report\n\nscore: 0.8\n'
    (root / 'source/workload.py').write_bytes(code)
    (root / 'source/generate_data.py').write_bytes(generated_source)
    (root / 'report.md').write_bytes(report)
    code_hash = hashlib.sha256(code).hexdigest()
    with store.connection(project) as connection:
        connection.execute("UPDATE runs SET state='COMPLETED',code_sha256=?,report_path='report.md' WHERE id=?",
                           (code_hash, run['id']))
        connection.executescript(WORKING_SCHEMA)
        saved_manifest = {'files': [{'path': 'source/generate_data.py', 'bytes': len(generated_source),
                                    'sha256': hashlib.sha256(generated_source).hexdigest()}]}
        connection.execute("INSERT INTO working_runs(run_id,session_id,phase,accelerator,ttl_seconds,started_at,manifest_json) "
                           "VALUES(?,?,'stopped','cpu',60,'fixture',?)",
                           (run['id'], run['id'], json.dumps(saved_manifest)))

    baseline, texts = view.variant_baseline(project, run['id'])
    generated_entry = next(item for item in baseline['text_files'] if item['path'] == 'source/generate_data.py')
    assert generated_entry['available'] is True
    assert generated_entry['stage_path'] == 'baseline/source/generate_data.py'
    assert generated_entry['sha256'] == hashlib.sha256(generated_source).hexdigest()
    request_id = '1' * 32
    args = (project, run['id'], request_id, '  Variant  ', 'new purpose', 'change model')
    with pytest.raises(StoreConflict, match='chưa xác nhận'):
        store.create_variant_idea(*args, baseline, texts)
    with store.connection(project) as connection:
        connection.execute('UPDATE working_runs SET stop_confirmed=1 WHERE run_id=?', (run['id'],))
        for state in ('RUNNING', 'UNKNOWN'):
            connection.execute('UPDATE runs SET state=? WHERE id=?', (state, run['id']))
            with pytest.raises(StoreConflict, match='chưa kết thúc'):
                store._variant_parent(connection, run['id'])
        connection.execute("UPDATE runs SET deleted_at='fixture' WHERE id=?", (run['id'],))
        with pytest.raises(StoreConflict, match='đã bị ẩn'):
            store._variant_parent(connection, run['id'])
        connection.execute('UPDATE runs SET state=\'COMPLETED\',deleted_at=NULL WHERE id=?', (run['id'],))

    first = store.create_variant_idea(*args, baseline, texts)
    replay = store.create_variant_idea(*args, baseline, texts)
    assert first['id'] == replay['id'] and first['state'] == 'DRAFT'
    assert first['title'] == 'Variant' and first['variant']['parent_run_id'] == run['id']
    with pytest.raises(StoreConflict, match='nội dung biến thể khác'):
        store.create_variant_idea(project, run['id'], request_id, 'Variant', 'changed purpose', 'change model', baseline, texts)
    with pytest.raises(StoreConflict, match='parent hoặc nội dung'):
        store.create_variant_idea(project, '2' * 32, request_id, 'Variant', 'new purpose', 'change model', baseline, texts)
    with pytest.raises(KeyError):
        view.variant_baseline(other_project, run['id'])

    snapshot = store.context_snapshot(project, first['id'], [store.resources(project)[0]['id']])['snapshot']
    staged = store.variant_stage_files(snapshot)
    assert staged['baseline/report.md'] == report
    assert staged['baseline/workload.py'] == code
    assert staged['baseline/source/generate_data.py'] == generated_source
    proposal_id = store.save_proposal(project, first['id'], ready(snapshot['resources'][0]['id']),
                                      store.context_snapshot(project, first['id'], [snapshot['resources'][0]['id']]))
    with store.connection(project) as connection:
        connection.execute('UPDATE variant_ideas SET baseline_text_json=? WHERE idea_id=?', ('{}', first['id']))
    with pytest.raises(StoreConflict, match='Baseline'):
        store.approve_proposal(project, proposal_id, 1, store.proposals(project)[0]['context_sha256'])

    assert hashlib.sha256((root / 'source/workload.py').read_bytes()).hexdigest() == code_hash
    assert hashlib.sha256((root / 'report.md').read_bytes()).hexdigest() == hashlib.sha256(report).hexdigest()


def test_variant_can_use_parent_without_saved_code_or_report(tmp_path):
    store = ProjectStore(tmp_path / '.workbench/projects')
    project, run = approved_run(store)
    with store.connection(project) as connection:
        connection.execute("UPDATE runs SET state='FAILED' WHERE id=?", (run['id'],))
    view = RunView(store, tmp_path, lambda: False)
    baseline, texts = view.variant_baseline(project, run['id'])
    assert texts == {}
    assert all(not item['available'] for item in baseline['text_files'])
    idea = store.create_variant_idea(project, run['id'], '2' * 32, 'Fallback', 'new purpose',
                                     'change the output format', baseline, texts)
    context = store.context_snapshot(project, idea['id'], [store.resources(project)[0]['id']])['snapshot']
    staged = store.variant_stage_files(context)
    assert set(staged) == {'baseline/manifest.json'}
    proposal_id = store.save_proposal(project, idea['id'], ready(context['resources'][0]['id']),
                                      store.context_snapshot(project, idea['id'], [context['resources'][0]['id']]))
    unapproved_run_id = '3' * 32
    with store.connection(project) as connection:
        connection.execute("INSERT INTO runs(id,proposal_id,state,intent_key,artifact_dir) VALUES(?,?,'APPROVED',?,?)",
                           (unapproved_run_id, proposal_id, 'fixture-unapproved', 'runs/' + unapproved_run_id))
    with pytest.raises(StoreConflict, match='approved'):
        WorkingStore(store).reserve(project, unapproved_run_id, 'cpu', 60)
