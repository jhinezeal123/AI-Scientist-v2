"""Project-owned Etc bundles; execution and collection use the shared Working path."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import PurePosixPath

from .modes import snapshot_settings
from .named_paths import PATH_LOCK, checked_child, folder_title, filesystem_path
from .store import StoreConflict


def prepare_output(store, project_id, run_id, approved):
    if snapshot_settings(approved['snapshot'], require_output=True)[0] != 'etc':
        raise ValueError('Only an approved Etc request belongs in project/output')
    with PATH_LOCK, store.connection(project_id) as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT artifact_dir FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise KeyError('Run not found in this project')
        if row['artifact_dir'].startswith('output/'):
            return store.run_root(project_id, run_id, store.workspace)
        if row['artifact_dir'] != f'runs/{run_id}':
            raise ValueError('Etc cannot move an existing research experiment')
        old = store.run_root(project_id, run_id, store.workspace)
        container = filesystem_path(checked_child(store.directory(project_id), 'output'))
        container.mkdir(exist_ok=True)
        idea = store.idea(project_id, approved['snapshot']['idea']['id'])
        title = folder_title(idea['title'] or approved['body']['objective'][:70]).replace(' ', '_')[:85]
        stem = f'{datetime.now():%Y-%m-%d}_{title}_attempt_'
        attempt = 0
        while (container / f'{stem}{attempt}').exists():
            attempt += 1
        root = checked_child(container, f'{stem}{attempt}')
        if old.exists():
            old.rename(root)
        else:
            root.mkdir()
        try:
            context = {'project_id': project_id, 'run_id': run_id, 'attempt': attempt, 'approved': approved}
            (root / 'context.json').write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding='utf-8')
            connection.execute('UPDATE runs SET artifact_dir=? WHERE id=?', ('output/' + root.name, run_id))
        except BaseException:
            old.parent.mkdir(parents=True, exist_ok=True)
            root.rename(old)
            raise
        return root


def save_output(store, root, project_id, run_id, approved, record, receipt, outcome):
    """Save user-facing content and collection evidence without a generated report."""
    summary = record['summary'] or {
        'summary': 'Working dừng trước khi agent trả kết quả cuối.', 'limitations': ['Chưa xác minh hoàn tất công việc.']}
    result = {
        'project_id': project_id, 'run_id': run_id, 'mode': 'etc',
        'context_sha256': approved['context_sha256'],
        'desired_output': snapshot_settings(approved['snapshot'])[1],
        'outcome': outcome, 'stop_confirmed': True, 'stop': receipt,
        'summary': summary['summary'], 'limitations': summary.get('limitations', []),
        'manifest': record['manifest'],
    }
    path = root / 'output.json'
    temporary = root / 'output.json.tmp'
    if path.is_symlink() or temporary.is_symlink():
        raise ValueError('Linked Output metadata refused')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
    if record['manifest'] is not None:
        manifest_path = root / 'working-manifest.json'
        if manifest_path.is_symlink() or manifest_path.is_junction():
            raise ValueError('Linked Output manifest refused')
        manifest_path.write_text(json.dumps(record['manifest'], indent=2), encoding='utf-8')
    log = root / 'working.log'
    if log.is_symlink() or log.is_junction():
        raise ValueError('Linked Output log refused')
    with store.connection(project_id) as connection, log.open('w', encoding='utf-8') as stream:
        for row in connection.execute('SELECT text FROM logs WHERE run_id=? ORDER BY generation,seq', (run_id,)):
            stream.write(row['text'])


def output_detail(root, record, artifact_dir, state, artifacts):
    summary = (record or {}).get('summary') or {}
    files = [item for item in ((record or {}).get('manifest') or {}).get('files', [])
             if item['path'] in artifacts]
    return {
        'directory': str(root) if artifact_dir.startswith('output/') else None,
        'status': 'completed' if state == 'COMPLETED' else 'partial' if state in {'FAILED', 'CANCELLED'} else 'pending',
        'summary': summary.get('summary', ''), 'limitations': summary.get('limitations', []),
        'summary_sha256': hashlib.sha256(summary['summary'].encode('utf-8')).hexdigest()
            if summary.get('summary', '').strip() else None,
        'files': files, 'stop_confirmed': bool(record and record['stop_confirmed']),
    }


def copy_to_library(store, project_id, run_id, record, *, kind, title, sha256, path=None):
    """Copy selected, verified bytes into the existing Library import pipeline."""
    from .ingestion import MAX_FILE_BYTES
    run = store.run(project_id, run_id)
    approved = store.approved_snapshot(project_id, run_id)
    if run['deleted_at'] or snapshot_settings(approved['snapshot'])[0] != 'etc' or record is None:
        raise StoreConflict('Chọn Output của một Run Etc chưa bị xóa')
    if not title.strip():
        raise ValueError('Nhập tiêu đề nguồn Library')
    summary = record['summary'] or {}
    if kind == 'text':
        if path is not None:
            raise ValueError('Nội dung Output không có đường dẫn file')
        text = summary.get('summary', '')
        if not text.strip():
            raise StoreConflict('Run chưa có nội dung Output để copy')
        filename, data = 'output.txt', text.encode('utf-8')
    elif kind == 'file':
        name = PurePosixPath(path or '')
        if (name.is_absolute() or len(name.parts) < 2 or name.parts[0] not in {'source', 'output'}
                or name.as_posix() != path or any(part in {'.', '..'} or ':' in part or '\\' in part for part in name.parts)):
            raise ValueError('Chọn đúng đường dẫn file Output đã thu')
        item = next((item for item in (record['manifest'] or {}).get('files', []) if item['path'] == path), None)
        if item is None or item['sha256'] != sha256:
            raise StoreConflict('File đã thay đổi hoặc chưa được thu; tải lại Output rồi chọn lại')
        if item['bytes'] > MAX_FILE_BYTES:
            raise ValueError('File vượt giới hạn nhập 25 MB hiện tại của Library')
        root = store.run_root(project_id, run_id, store.workspace)
        target = root.joinpath(*name.parts)
        if (not target.resolve().is_relative_to(root.resolve()) or any(
                part.is_symlink() or part.is_junction() for part in (target, *target.parents)
                if part.is_relative_to(root))):
            raise ValueError('Linked Output file refused')
        if not target.is_file() or target.stat().st_size != item['bytes']:
            raise StoreConflict('File Output không còn khớp manifest đã thu')
        with target.open('rb') as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) != item['bytes']:
            raise StoreConflict('File Output thay đổi trong khi đọc; tải lại rồi chọn lại')
        filename = name.name
    else:
        raise ValueError('Chọn file hoặc nội dung Output')
    actual_sha256 = hashlib.sha256(data).hexdigest()
    if actual_sha256 != sha256:
        raise StoreConflict('Output đã thay đổi; tải lại và chọn kết quả hiện hành trước khi copy')
    provenance = {
        'kind': 'etc_output', 'project_id': project_id, 'run_id': run_id,
        'proposal_id': run['proposal_id'], 'proposal_version': run['proposal_version'],
        'context_sha256': approved['context_sha256'], 'selection': kind, 'path': path,
        'sha256': actual_sha256, 'bytes': len(data),
        'copied_at': datetime.now(timezone.utc).isoformat(), 'run_state': run['state'],
        'output_status': 'completed' if run['state'] == 'COMPLETED'
            else 'partial' if run['state'] in {'FAILED', 'CANCELLED'} else 'pending',
        'stop_confirmed': record['stop_confirmed'], 'limitations': summary.get('limitations', []),
    }
    return store.import_file(project_id, title, filename, data, provenance=provenance)
