"""Project-wide run lineage and the compact memory passed to a child run."""
import hashlib
import json
from pathlib import PurePosixPath
from urllib.parse import quote

from .models import ResearchPlan

RUN_TAGS = {'research', 'tuning', 'ablation'}


def write_run_json(path, value):
    """Atomically persist a run file without loading the legacy search engine."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def run_settings(mode, research=None, tags=None):
    tags = tags or []
    if len(tags) != len(set(tags)) or any(tag not in RUN_TAGS for tag in tags):
        raise ValueError('Run tags must be distinct research, tuning or ablation labels')
    return (ResearchPlan.model_validate(research or {}).model_dump() if mode != 'etc' else None,
            list(tags) if mode != 'etc' else [])


def parent_id(run, snapshot):
    return (snapshot.get('variant') or {}).get('parent_run_id') or run.get('parent_run_id')


def artifact_reference(run_id, item):
    return {**item, 'title': PurePosixPath(item['path']).name,
            'link': f'artifact://{run_id}/' + quote(item['path'], safe='/')}


def memory_document(run, approved, record=None, receipt=None):
    """Small factual journal; no raw code, file contents or package inventories."""
    summary = (record or {}).get('summary') or {}
    return {'format': 1, 'run_id': run['id'], 'parent_run_id': parent_id(run, approved['snapshot']),
            'objective': approved['body']['objective'],
            'change_summary': (approved['snapshot'].get('variant') or {}).get('change_summary'),
            'state': (record or {}).get('outcome') or run['state'],
            'summary': summary.get('summary', ''), 'limitations': summary.get('limitations', []),
            'succeeded': summary.get('succeeded'),
            'stop_confirmed': bool((receipt or {}).get('stopped')),
            'artifacts': [artifact_reference(run['id'], item)
                          for item in ((record or {}).get('manifest') or {}).get('files', [])]}


def save_memory(store, root, project_id, run_id, approved, record, receipt):
    write_run_json(root / 'memory_journal.json', memory_document(
        store.run(project_id, run_id), approved, record, receipt))


def lazy_parent_file(store, workspace, project_id, snapshot, link):
    """Resolve only links pinned in this child's approved baseline."""
    variant = snapshot.get('variant') or {}
    item = next((item for item in variant.get('baseline', {}).get('artifact_refs', [])
                 if item.get('link') == link), None)
    if item is None:
        raise ValueError('Artifact link is outside the approved parent baseline')
    root = store.run_root(project_id, variant['parent_run_id'], workspace).resolve()
    parsed = PurePosixPath(item['path'])
    if parsed.is_absolute() or '..' in parsed.parts or '\\' in item['path']:
        raise ValueError('Invalid parent artifact path')
    path = root.joinpath(*parsed.parts)
    if (not path.is_file() or not path.resolve().is_relative_to(root)
            or any(p.is_symlink() or p.is_junction() for p in (path, *path.parents) if p.is_relative_to(root))
            or path.stat().st_size != item['bytes']):
        raise ValueError('Parent artifact is missing or changed')
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != item['sha256']:
            raise ValueError('Parent artifact hash changed')
    return 'baseline/artifacts/' + item['path'], path
