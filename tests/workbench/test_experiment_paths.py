"""Project packaging and lossless migration; no agent or Kaggle execution."""
import hashlib
import json
import shutil

import pytest

from ai_scientist.workbench.experiments import prepare_experiment
from ai_scientist.workbench.run_view import RunView
from ai_scientist.workbench.named_paths import filesystem_path
from ai_scientist.workbench.store import ProjectStore
from test_implementation import approved_run


def hashes(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}


def allocate(store, workspace):
    project, run = approved_run(store)
    root = prepare_experiment(store, workspace, project, run['id'],
                              store.approved_snapshot(project, run['id']))
    (root / 'report.md').write_text('preserved result', encoding='utf-8')
    return project, run['id'], root


def test_experiment_is_packaged_with_project_and_attempts_are_project_scoped(tmp_path):
    store = ProjectStore(tmp_path / '.workbench/projects', tmp_path)
    first, run, root = allocate(store, tmp_path)
    second, _, other = allocate(store, tmp_path)
    assert root.parent == filesystem_path(store.directory(first) / 'experiment')
    assert other.parent == filesystem_path(store.directory(second) / 'experiment')
    assert root.name == other.name and root.name.endswith('_attempt_0')
    assert not (tmp_path / 'experiments').exists()
    before = hashes(root)
    # Moving the whole project keeps run artifacts resolvable without its old workspace.
    portable = tmp_path / 'portable'
    (portable / '.workbench/projects').mkdir(parents=True)
    shutil.move(str(store.directory(first)), str(portable / '.workbench/projects' / store.directory(first).name))
    reopened = ProjectStore(portable / '.workbench/projects', portable)
    moved = RunView(reopened, portable, lambda: False).root(first, run)
    assert hashes(moved) == before


@pytest.mark.parametrize('already_moved', [False, True])
def test_external_experiment_migration_preserves_bytes_and_recovers_rename(tmp_path, already_moved):
    store = ProjectStore(tmp_path / '.workbench/projects', tmp_path)
    project, run, local = allocate(store, tmp_path)
    before = hashes(local)
    external = tmp_path / 'experiments' / local.name
    external.parent.mkdir()
    local.rename(external)
    with store.connection(project) as connection:
        connection.execute('UPDATE runs SET artifact_dir=? WHERE id=?', ('experiments/' + external.name, run))
    if already_moved:
        external.rename(local)
    reopened = ProjectStore(store.root, tmp_path)
    restored = reopened.run_root(project, run)
    assert restored == local and hashes(restored) == before
    assert reopened.run(project, run)['artifact_dir'] == 'experiment/' + local.name
    assert not external.parent.exists()
    assert ProjectStore(store.root, tmp_path).run_root(project, run) == restored


def test_external_migration_refuses_another_projects_folder(tmp_path):
    store = ProjectStore(tmp_path / '.workbench/projects', tmp_path)
    first, run, local = allocate(store, tmp_path)
    second = store.create_project('Other')['id']
    external = tmp_path / 'experiments' / local.name
    external.parent.mkdir()
    local.rename(external)
    marker = external / 'idea.json'
    data = json.loads(marker.read_text(encoding='utf-8'))
    data['workbench']['project_id'] = second
    marker.write_text(json.dumps(data), encoding='utf-8')
    before = hashes(external)
    with store.connection(first) as connection:
        connection.execute('UPDATE runs SET artifact_dir=? WHERE id=?', ('experiments/' + external.name, run))
    with pytest.raises(ValueError, match='ownership mismatch'):
        ProjectStore(store.root, tmp_path)
    assert hashes(external) == before and not local.exists()
    assert store.run(first, run)['artifact_dir'].startswith('experiments/')
