"""Narrowly validated provider runtime and sandbox directories."""
from pathlib import Path


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
