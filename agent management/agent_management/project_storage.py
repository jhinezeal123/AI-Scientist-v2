"""Project-owned team state and narrowly validated sandbox directories."""
import json
import hashlib
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3


def data_root(repository, workspace):
    for path in (Path(workspace), *Path(workspace).parents):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ValueError('Refusing redirected agent workspace')
        if path.resolve() == Path(repository).resolve():
            break
    repository, workspace = Path(repository).resolve(), Path(workspace).resolve()
    candidate = workspace.parents[2]
    global_root = repository / '.workbench/agents'
    projects = repository / '.workbench/projects'
    valid = candidate == global_root or (candidate.name == 'agents' and candidate.parent.parent == projects)
    if not valid or workspace.parent.parent != candidate / 'worktrees':
        raise ValueError('Workspace must belong to managed agent storage')
    for path in (candidate, *candidate.parents):
        if path == repository:
            break
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise ValueError('Refusing redirected project agent storage')
    return candidate


def migrate_team(source, target, rig_id, workspaces):
    """Move a legacy team in one attached-database transaction; retain a backup."""
    from .migrations import backup_database
    backup = source.path.with_name(source.path.name + '.before-project-storage.bak')
    if not backup.exists():
        backup_database(source.path, backup)
    with source.connect() as con:
        active = con.execute("SELECT 1 FROM sessions WHERE rig_id=? AND state IN ('STARTING','RUNNING','UNKNOWN')", (rig_id,)).fetchone()
        if active:
            raise ValueError('Reconcile existing team sessions before moving project storage')
        seats = con.execute('SELECT * FROM seats WHERE rig_id=?', (rig_id,)).fetchall()
        tasks = con.execute('SELECT * FROM tasks WHERE rig_id=?', (rig_id,)).fetchall()
    replacements = {}
    runtime_moves = []
    worktree_moves = []
    for seat in seats:
        if not seat['worktree']:
            continue
        old = Path(seat['worktree'])
        new = workspaces.path(rig_id, seat['id'])
        legacy = workspaces.repository / '.workbench/agents/worktrees' / rig_id / seat['id']
        if old.resolve() != legacy.resolve():
            raise ValueError('Legacy seat path is outside managed storage')
        if not old.exists() and not new.exists():
            raise ValueError('Legacy seat workspace is missing')
        replacements[str(old)] = str(new)
        old_key = hashlib.sha256(str(old.resolve()).encode()).hexdigest()
        new_key = hashlib.sha256(str(new.resolve()).encode()).hexdigest()
        runtimes = workspaces.repository/'.workbench/agents/runtimes'
        if runtimes.exists():
            for home in runtimes.glob('*-' + old_key):
                runtime_moves.append((home, workspaces.root.parent/'runtimes'/home.name.replace(old_key,new_key)))
    for task in tasks:
        if json.loads(task['payload_json']).get('kind') == 'terminal':
            key = hashlib.sha256(json.dumps([rig_id,task['seat'],task['request_id']]).encode()).hexdigest()
            home = workspaces.repository/'.workbench/agents/runtimes'/('terminal-'+key)
            if home.exists():
                runtime_moves.append((home, workspaces.root.parent/'runtimes'/home.name))
    filters = {'rigs': 'id=?', 'rig_runtime': 'rig_id=?', 'seats': 'rig_id=?',
               'tasks': 'rig_id=?', 'messages': 'rig_id=?', 'events': 'rig_id=?',
               'sessions': 'rig_id=?', 'journal': 'rig_id=?', 'snapshots': 'rig_id=?',
               'resources': 'rig_id=?', 'outbox': 'rig_id=?',
               'permissions': 'session_id IN (SELECT id FROM main.sessions WHERE rig_id=?)',
               'bridge_claims': 'request_id IN (SELECT request_id FROM main.outbox WHERE rig_id=?)'}
    try:
        for old_name, new_name in replacements.items():
            old, new = Path(old_name), Path(new_name)
            if old.exists():
                new.parent.mkdir(parents=True, exist_ok=True)
                workspaces.git(workspaces.repository, 'worktree', 'move', str(old), str(new))
                worktree_moves.append((old_name,new_name))
        for old, new in runtime_moves:
            if new.exists() or any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (old,*old.rglob('*'))):
                raise ValueError('Refusing redirected or conflicting runtime migration')
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old),str(new))
        with closing(sqlite3.connect(source.path, timeout=15)) as con:
            con.execute('ATTACH DATABASE ? AS project', (str(target.path),))
            con.execute('BEGIN IMMEDIATE')
            for table, condition in filters.items():
                con.execute(f'INSERT INTO project.{table} SELECT * FROM main.{table} WHERE {condition}', (rig_id,))
            for old, new in replacements.items():
                con.execute('UPDATE project.seats SET worktree=? WHERE rig_id=? AND worktree=?', (new, rig_id, old))
                for table, column in [('snapshots', 'descriptor_json'), ('journal', 'data_json')]:
                    rows = con.execute(f'SELECT rowid,{column} FROM project.{table} WHERE rig_id=?', (rig_id,)).fetchall()
                    for rowid, body in rows:
                        # JSON escapes Windows separators; replace decoded strings recursively.
                        def replace(value):
                            if isinstance(value, str):
                                return value.replace(old, new)
                            if isinstance(value, list):
                                return [replace(v) for v in value]
                            if isinstance(value, dict):
                                return {k: replace(v) for k, v in value.items()}
                            return value
                        con.execute(f'UPDATE project.{table} SET {column}=? WHERE rowid=?', (json.dumps(replace(json.loads(body))), rowid))
            for table, condition in reversed(list(filters.items())):
                con.execute(f'DELETE FROM main.{table} WHERE {condition}', (rig_id,))
            con.commit()
    except Exception:
        for old, new in reversed(runtime_moves):
            if new.exists() and not old.exists():
                shutil.move(str(new),str(old))
        for old, new in reversed(worktree_moves):
            workspaces.git(workspaces.repository, 'worktree', 'move', new, old)
        raise
