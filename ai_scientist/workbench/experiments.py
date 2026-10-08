"""Allocate upstream-style experiment directories for owned Workbench runs."""
from datetime import datetime
import json

from .named_paths import PATH_LOCK, checked_child, folder_title, filesystem_path


def prepare_experiment(store, workspace, project_id, run_id, approved):
    with PATH_LOCK, store.connection(project_id) as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT artifact_dir FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise KeyError('Run not found in this project')
        if row['artifact_dir'].startswith('experiment/'):
            return store.run_root(project_id, run_id, workspace)
        old = store.run_root(project_id, run_id, workspace)
        experiments = filesystem_path(checked_child(store.directory(project_id), 'experiment'))
        experiments.mkdir(exist_ok=True)
        idea = store.idea(project_id, approved['snapshot']['idea']['id'])
        title = folder_title(idea['title'] or approved['body']['objective'][:70]).replace(' ', '_')[:85]
        stem = f'{datetime.now():%Y-%m-%d}_{title}_attempt_'
        attempt = 0
        while (experiments / f'{stem}{attempt}').exists():
            attempt += 1
        root = checked_child(experiments, f'{stem}{attempt}')
        if old.exists():
            old.rename(root)
        else:
            root.mkdir()
        try:
            connection.execute('UPDATE runs SET artifact_dir=? WHERE id=?',
                               ('experiment/' + root.name, run_id))
            # Keep original upstream keys so this description is portable to its launcher.
            description = {'Name': title, 'Title': idea['title'] or approved['body']['objective'],
                'Abstract': approved['body']['paraphrase'],
                'Short Hypothesis': approved['body']['objective'],
                'Experiments': approved['body']['implementation_steps'],
                'Risk Factors and Limitations': [],
                'workbench': {'project_id': project_id, 'run_id': run_id, 'attempt': attempt,
                              'approved': approved}}
            (root / 'idea.json').write_text(json.dumps(description, ensure_ascii=False, indent=2), encoding='utf-8')
            from ai_scientist.treesearch.bfts_utils import idea_to_markdown
            idea_to_markdown(description, str(root / 'idea.md'), None)
            (root / 'logs/0-run').mkdir(parents=True, exist_ok=True)
        except BaseException:
            old.parent.mkdir(parents=True, exist_ok=True)
            root.rename(old)
            raise
        return root


def migrate_project_experiments(store, project_id):
    """Move only this project's registered external experiments, preserving bytes."""
    with PATH_LOCK:
        with store.connection(project_id) as connection:
            runs = [dict(row) for row in connection.execute(
                "SELECT id,artifact_dir FROM runs WHERE artifact_dir LIKE 'experiments/%'")]
        for run in runs:
            old = store.run_root(project_id, run['id'], store.workspace)
            container = filesystem_path(checked_child(store.directory(project_id), 'experiment'))
            destination = checked_child(container, old.name)
            # A crash after rename but before SQLite commit leaves the folder at
            # its destination. Verify ownership before repairing the DB pointer.
            if old.exists() and destination.exists():
                raise FileExistsError(f'Experiment migration destination already exists: {destination}')
            evidence = old if old.exists() else destination
            marker = checked_child(evidence, 'idea.json')
            if not evidence.is_dir() or not marker.is_file():
                raise FileNotFoundError(f'Experiment migration source missing: {old}')
            owner = json.loads(marker.read_text(encoding='utf-8')).get('workbench', {})
            if owner.get('project_id') != project_id or owner.get('run_id') != run['id']:
                raise ValueError('Experiment migration ownership mismatch')
            moved = False
            try:
                with store.connection(project_id) as connection:
                    connection.execute('BEGIN IMMEDIATE')
                    if old.exists():
                        container.mkdir(exist_ok=True)
                        old.rename(destination)
                        moved = True
                    connection.execute('UPDATE runs SET artifact_dir=? WHERE id=?',
                                       ('experiment/' + destination.name, run['id']))
            except BaseException:
                if moved:
                    destination.rename(old)
                raise
        # Remove only the now-empty legacy container. Unregistered upstream
        # experiments stay intact; never scan or delete them recursively.
        if runs:
            legacy = checked_child(store.workspace, 'experiments')
            if legacy.is_dir() and not any(legacy.iterdir()):
                legacy.rmdir()


def search_artifacts(root):
    """List saved tree evidence, excluding gateways, credentials and agent workspaces."""
    names = ['idea.md', 'idea.json', 'token_tracker.json', 'review_text.txt',
             'logs/0-run/search-state.json', 'logs/0-run/unified_tree_viz.html']
    logs = root / 'logs/0-run'
    if logs.is_dir() and not logs.is_symlink() and not logs.is_junction():
        for path in logs.rglob('*'):
            if not path.is_file() or path.is_symlink() or path.is_junction():
                continue
            relative = path.relative_to(root).as_posix()
            if (any(part in {'working-agent', 'library', 'baseline'} for part in path.relative_to(logs).parts)
                    or any(p.is_symlink() or p.is_junction() for p in path.parents if p != root and p.is_relative_to(root))):
                continue
            names.append(relative)
    names.extend(path.name for path in root.glob('*.pdf'))
    return sorted({name for name in names if (root / name).is_file()
                   and not (root / name).is_symlink() and not (root / name).is_junction()})
