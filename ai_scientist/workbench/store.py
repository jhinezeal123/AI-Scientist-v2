"""Project-scoped SQLite authority. Every operation owns a short connection."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import uuid

from .library import LibraryFiles
from .named_paths import PATH_LOCK, checked_child, folder_title, rename_folder, unique_title, filesystem_path


SCHEMA = """
CREATE TABLE IF NOT EXISTS project_meta(id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, schema_version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, url TEXT, content TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL, content_sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ideas(id TEXT PRIMARY KEY, text TEXT NOT NULL, conversation_json TEXT NOT NULL, state TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', deleted_at TEXT);
CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, idea_id TEXT NOT NULL REFERENCES ideas(id), version INTEGER NOT NULL, body_json TEXT NOT NULL, context_snapshot_json TEXT NOT NULL, context_sha256 TEXT NOT NULL, state TEXT NOT NULL, approved_at TEXT);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id), node_id TEXT, node_json TEXT, state TEXT NOT NULL, intent_key TEXT UNIQUE NOT NULL, code_sha256 TEXT, identity_json TEXT, artifact_dir TEXT NOT NULL, error TEXT, report_path TEXT, deleted_at TEXT);
CREATE TABLE IF NOT EXISTS logs(run_id TEXT NOT NULL REFERENCES runs(id), generation INTEGER NOT NULL, seq INTEGER NOT NULL, text TEXT NOT NULL, stream TEXT NOT NULL, UNIQUE(run_id,generation,seq));
"""

IMPLEMENTATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS implementation_attempts(
run_id TEXT NOT NULL REFERENCES runs(id), attempt INTEGER NOT NULL,
request_id TEXT NOT NULL UNIQUE, state TEXT NOT NULL, node_json TEXT,
session_id TEXT, checks_json TEXT, error TEXT, origin TEXT NOT NULL DEFAULT 'CODEX', PRIMARY KEY(run_id,attempt));
CREATE TABLE IF NOT EXISTS run_retries(
run_id TEXT PRIMARY KEY REFERENCES runs(id), parent_run_id TEXT NOT NULL REFERENCES runs(id),
request_id TEXT NOT NULL UNIQUE);
"""

INGESTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_ingestions(resource_id TEXT NOT NULL REFERENCES resources(id),
version INTEGER NOT NULL, metadata_json TEXT NOT NULL, PRIMARY KEY(resource_id,version));
"""

DELETION_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_deletions(resource_id TEXT PRIMARY KEY REFERENCES resources(id),
plan_json TEXT NOT NULL, error TEXT);
"""

VARIANT_SCHEMA = """
CREATE TABLE IF NOT EXISTS variant_ideas(
idea_id TEXT PRIMARY KEY REFERENCES ideas(id), parent_run_id TEXT NOT NULL REFERENCES runs(id),
parent_proposal_id TEXT NOT NULL REFERENCES proposals(id), purpose TEXT NOT NULL, change_summary TEXT NOT NULL,
created_at TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE, request_sha256 TEXT NOT NULL,
variant_json TEXT NOT NULL, baseline_text_json TEXT NOT NULL);
"""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_VARIANT_SOURCE_EXTENSIONS = {
    '.py', '.pyw', '.r', '.jl', '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
    '.sh', '.bash', '.sql', '.java', '.c', '.h', '.cc', '.cpp', '.go', '.rs',
    '.lua', '.rb', '.swift', '.kt', '.scala',
}
_VARIANT_SECRET_NAMES = {
    '.env', '.env.local', '.env.production', 'terminal-access.json',
    'credentials.json', 'secrets.json', 'tokens.json', 'id_rsa', 'id_ed25519',
}


def _safe_variant_source_path(value):
    if not isinstance(value, str) or not value or '\\' in value:
        return False
    parsed = PurePosixPath(value)
    if (parsed.is_absolute() or parsed.parts[0] != 'source' or len(parsed.parts) < 2
            or parsed.as_posix() != value or any(part in {'', '.', '..'} for part in parsed.parts)):
        return False
    lowered = [part.lower() for part in parsed.parts]
    return (not any(part in {'credentials', 'secrets'} or part in _VARIANT_SECRET_NAMES for part in lowered)
            and parsed.suffix.lower() in _VARIANT_SOURCE_EXTENSIONS)


def _valid_variant_stage(item):
    if not isinstance(item, dict):
        return False
    path, stage_path = item.get('path'), item.get('stage_path')
    if stage_path == 'baseline/report.md':
        return path == 'report.md'
    if stage_path == 'baseline/workload.py':
        return path == 'source/workload.py'
    return path != 'source/workload.py' and _safe_variant_source_path(path) and stage_path == f'baseline/{path}'


def idea_title(title):
    title = " ".join(title.split())
    if not title or len(title) > 80:
        raise ValueError("Tiêu đề idea phải có từ 1 đến 80 ký tự")
    return title


class StoreConflict(ValueError):
    pass


class ProjectStore:
    def run_root(self, project_id, run_id, workspace=None):
        """Resolve an owned run's persisted artifact location."""
        run = self.run(project_id, run_id)
        relative = PurePosixPath(run['artifact_dir'])
        if relative.is_absolute() or '\\' in run['artifact_dir'] or '..' in relative.parts:
            raise ValueError('Invalid run artifact directory')
        if relative.parts[:1] == ('experiments',):
            if workspace is None or len(relative.parts) != 2:
                raise ValueError('Experiment location requires its workspace')
            root = Path(workspace).resolve()
        else:
            if relative.parts != ('runs', run_id) and not (len(relative.parts) == 2 and relative.parts[0] == 'experiment'):
                raise ValueError('Invalid legacy run location')
            root = self.directory(project_id)
        if relative.parts[0] in {'experiment', 'experiments'}:
            root = filesystem_path(root)
        path = root.joinpath(*relative.parts)
        for parent in (path, *path.parents):
            if parent == root.parent:
                break
            if parent.is_symlink() or parent.is_junction():
                raise ValueError('Linked run artifact directory')
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Run artifact directory escapes its project')
        return path

    def __init__(self, root: Path, workspace: Path | None = None):
        self.root = root.resolve()
        self.workspace = Path(workspace).resolve() if workspace else (self.root.parent.parent if self.root.parent.name == '.workbench' else self.root.parent)
        self.root.mkdir(parents=True, exist_ok=True)
        self._directories = {}
        self._discover_projects()
        for project in self.list_projects():
            self._name_project_directory(project['id'])
            with self.connection(project['id']) as connection:
                self._migrate_schema(connection)
                pending = [row[0] for row in connection.execute('SELECT resource_id FROM source_deletions')]
            from .experiments import migrate_project_experiments
            migrate_project_experiments(self, project['id'])
            for resource_id in pending:
                try:
                    self.delete_resource(project['id'], resource_id)
                except (StoreConflict, ValueError):
                    pass  # Keep a visible retry action; never recreate files from a pending deletion.
            with self.connection(project['id']) as connection:
                sources = [dict(row) for row in connection.execute('SELECT * FROM resources WHERE id NOT IN (SELECT resource_id FROM source_deletions)')]
            for source in sources:
                title = self.library(project['id']).register(source)
                if title != source['title']:
                    self.save_resource(project['id'], {**source, 'title':title}, source['id'], source['version'])
                else:
                    self.library(project['id']).reference(source)

    def _discover_projects(self):
        with PATH_LOCK:
            directories = {}
            for directory in self.root.iterdir():
                if not directory.is_dir() or directory.is_symlink() or directory.is_junction():
                    continue
                database = directory / 'project.sqlite'
                if not database.is_file() or database.is_symlink():
                    continue
                connection = sqlite3.connect(database)
                try:
                    row = connection.execute('SELECT id FROM project_meta').fetchone()
                finally:
                    connection.close()
                if row is None or not re.fullmatch(r'[0-9a-f]{32}', row[0]):
                    raise ValueError('Invalid project database identity')
                if row[0] in directories:
                    raise ValueError('Duplicate project database identity')
                directories[row[0]] = directory
            self._directories = directories

    def _name_project_directory(self, project_id):
        with PATH_LOCK:
            old = self.directory(project_id)
            with self.connection(project_id) as connection:
                title = connection.execute('SELECT name FROM project_meta WHERE id=?', (project_id,)).fetchone()[0]
            name = unique_title(folder_title(title), [item.name for item in self.root.iterdir() if item != old])
            destination = checked_child(self.root, name)
            if old.name != name:
                rename_folder(old, destination)
                self._directories[project_id] = destination
            with self.connection(project_id) as connection:
                connection.execute('UPDATE project_meta SET name=? WHERE id=?', (name, project_id))

    @staticmethod
    def _migrate_schema(connection):
        """Keep upgrades of existing project databases in one place."""
        connection.executescript(IMPLEMENTATION_SCHEMA)
        connection.executescript(INGESTION_SCHEMA)
        connection.executescript(DELETION_SCHEMA)
        connection.executescript(VARIANT_SCHEMA)
        if 'title' not in {row['name'] for row in connection.execute('PRAGMA table_info(ideas)')}:
            connection.execute("ALTER TABLE ideas ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        if 'origin' not in {row['name'] for row in connection.execute('PRAGMA table_info(implementation_attempts)')}:
            connection.execute("ALTER TABLE implementation_attempts ADD COLUMN origin TEXT NOT NULL DEFAULT 'CODEX'")
        for table in ('ideas', 'runs'):
            if 'deleted_at' not in {row['name'] for row in connection.execute(f'PRAGMA table_info({table})')}:
                connection.execute(f'ALTER TABLE {table} ADD COLUMN deleted_at TEXT')
        connection.execute('UPDATE project_meta SET schema_version=7 WHERE schema_version<7')

    def library(self, project_id):
        return LibraryFiles(self.directory(project_id), lambda resource, version:self.ingestion(project_id, resource, version),
                            lambda resource:self.source_available(project_id, resource))

    def source_available(self, project_id, resource_id):
        with self.connection(project_id) as connection:
            return connection.execute('SELECT 1 FROM resources WHERE id=? AND id NOT IN (SELECT resource_id FROM source_deletions)',
                                      (resource_id,)).fetchone() is not None

    def ingestion(self, project_id, resource_id, version):
        with self.connection(project_id) as connection:
            row = connection.execute('SELECT metadata_json FROM source_ingestions WHERE resource_id=? AND version=?',
                                     (resource_id, version)).fetchone()
            return json.loads(row[0]) if row else None

    def directory(self, project_id):
        """Resolve all project files through the same ownership-checked path."""
        return self._path(project_id).parent

    def _path(self, project_id):
        if not re.fullmatch(r"[0-9a-f]{32}", project_id):
            raise KeyError("Project not found")
        directory = self._directories.get(project_id)
        if directory is None:
            raise KeyError('Project not found')
        if directory.is_symlink() or directory.is_junction() or not directory.resolve().is_relative_to(self.root):
            raise KeyError("Project not found")
        database = directory / "project.sqlite"
        if database.is_symlink():
            raise KeyError("Project not found")
        return database

    @contextmanager
    def connection(self, project_id):
        path = self._path(project_id)
        if not path.is_file():
            raise KeyError("Project not found")
        connection = sqlite3.connect(path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create_project(self, name):
        with PATH_LOCK:
            name = unique_title(folder_title(name), [item.name for item in self.root.iterdir()])
            project_id = uuid.uuid4().hex
            directory = checked_child(self.root, name)
            directory.mkdir()
            (directory / 'library').mkdir()
            self._directories[project_id] = directory
            connection = sqlite3.connect(directory / 'project.sqlite')
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.executescript(SCHEMA)
                connection.executescript(IMPLEMENTATION_SCHEMA)
                connection.executescript(INGESTION_SCHEMA)
                connection.executescript(DELETION_SCHEMA)
                connection.executescript(VARIANT_SCHEMA)
                connection.execute("INSERT INTO project_meta VALUES(?,?,?,7)",
                                   (project_id, name, datetime.now(timezone.utc).isoformat()))
                connection.commit()
            finally:
                connection.close()
        return self.project(project_id)

    def project(self, project_id):
        with self.connection(project_id) as connection:
            row = connection.execute("SELECT * FROM project_meta WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise KeyError("Project not found")
            return {**dict(row), 'directory_name':self.directory(project_id).name,
                    'library_path':str(self.directory(project_id) / 'library')}

    def list_projects(self):
        self._discover_projects()
        projects = [self.project(project_id) for project_id in tuple(self._directories)]
        return sorted(projects, key=lambda project: project["created_at"], reverse=True)

    def resources(self, project_id):
        with self.connection(project_id) as connection:
            pending = {row['resource_id']:row['error'] for row in connection.execute('SELECT * FROM source_deletions')}
            return [({**dict(row), 'deletion_pending':True, 'deletion_error':pending[row['id']]}
                     if row['id'] in pending else {**dict(row), **self.library(project_id).reference(dict(row))})
                    for row in connection.execute("SELECT * FROM resources ORDER BY rowid")]

    def save_resource(self, project_id, body, resource_id=None, expected_version=None):
        title, content = body["title"].strip(), body["content"]
        from .resources import source_has_text, source_urls
        urls = source_urls(body)
        url = body.get("url") or next(iter(urls), None)
        status = "provided_text" if source_has_text(content, urls) else "reference_only"
        if not title or (not content.strip() and not url):
            raise ValueError("A title and text or URL are required")
        with PATH_LOCK, self.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            if resource_id is None:
                resource_id, version = uuid.uuid4().hex, 1
            else:
                existing = connection.execute("SELECT version FROM resources WHERE id=?", (resource_id,)).fetchone()
                if existing is None:
                    raise KeyError("Resource not found in this project")
                if not self.source_available(project_id, resource_id):
                    raise StoreConflict('Nguồn đang xóa hoặc đã bị xóa')
                if existing["version"] != expected_version:
                    raise StoreConflict("Resource changed; reload before saving")
                version = existing["version"] + 1
            title = self.library(project_id).register({'id':resource_id, 'title':title})
            kind = body.get('kind') or ('url' if url else 'text')
            row = {"id": resource_id, "kind": kind, "title": title, "url": url,
                   "content": content, "status": status, "version": version,
                   "content_sha256": digest(canonical({"kind": kind, "title": title,
                                                       "url": url, "content": content, "status": status}))}
            reference = self.library(project_id).reference(row, saving=True)
            self._write_resource(connection, row)
            return {**row, **reference}

    @classmethod
    def _write_resource(cls, connection, row):
        connection.execute("INSERT INTO resources(id,kind,title,url,content,status,version,content_sha256) VALUES(:id,:kind,:title,:url,:content,:status,:version,:content_sha256) "
                           "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,title=excluded.title,url=excluded.url,content=excluded.content,status=excluded.status,version=excluded.version,content_sha256=excluded.content_sha256", row)
        cls._invalidate_source_proposals(connection, row['id'])

    @staticmethod
    def _invalidate_source_proposals(connection, resource_id):
        for proposal in connection.execute("SELECT id,idea_id,context_snapshot_json FROM proposals WHERE state IN ('AWAITING_APPROVAL','NEEDS_CLARIFICATION')").fetchall():
            if any(source['id'] == resource_id for source in json.loads(proposal['context_snapshot_json'])['resources']):
                connection.execute("UPDATE proposals SET state='STALE' WHERE id=?", (proposal['id'],))
                connection.execute("UPDATE ideas SET state='NEEDS_REVIEW' WHERE id=? AND state IN ('AWAITING_APPROVAL','NEEDS_CLARIFICATION')", (proposal['idea_id'],))

    def delete_resource(self, project_id, resource_id):
        from .source_deletion import deletion_plan, remove_source_files
        with PATH_LOCK:
            library = self.library(project_id)
            with self.connection(project_id) as connection:
                connection.execute('BEGIN IMMEDIATE')
                if connection.execute('SELECT 1 FROM resources WHERE id=?', (resource_id,)).fetchone() is None:
                    raise KeyError('Source not found in this project')
                if connection.execute("SELECT 1 FROM ideas WHERE state='PLANNING'").fetchone():
                    raise StoreConflict('Chờ project lập proposal xong trước khi xóa nguồn')
                for run in connection.execute("SELECT proposals.context_snapshot_json FROM runs JOIN proposals ON proposals.id=runs.proposal_id WHERE runs.state IN ('STARTING','WORKING','STOPPING','IMPLEMENTING','SUBMITTING')"):
                    if any(source['id'] == resource_id for source in json.loads(run[0])['resources']):
                        raise StoreConflict('Nguồn đang được run sử dụng; chờ run kết thúc trước khi xóa')
                pending = connection.execute('SELECT plan_json FROM source_deletions WHERE resource_id=?', (resource_id,)).fetchone()
                experiment_roots = {row['id']: self.run_root(project_id, row['id'], self.workspace)
                    for row in connection.execute("SELECT id FROM runs WHERE artifact_dir LIKE 'experiment/%' OR artifact_dir LIKE 'experiments/%'")}
                plan = json.loads(pending[0]) if pending else deletion_plan(library, resource_id, experiment_roots)
                connection.execute('INSERT OR IGNORE INTO source_deletions VALUES(?,?,NULL)', (resource_id, canonical(plan)))
                self._invalidate_source_proposals(connection, resource_id)
            try:
                remove_source_files(library, resource_id, plan, experiment_roots)
            except (OSError, ValueError) as exc:
                error = 'Chưa xóa hết file. Đóng file/thư mục đang mở rồi bấm Xóa lại.'
                with self.connection(project_id) as connection:
                    connection.execute('UPDATE source_deletions SET error=? WHERE resource_id=?', (error, resource_id))
                raise StoreConflict(error) from exc
            with self.connection(project_id) as connection:
                connection.execute('DELETE FROM source_deletions WHERE resource_id=?', (resource_id,))
                connection.execute('DELETE FROM source_ingestions WHERE resource_id=?', (resource_id,))
                connection.execute('DELETE FROM resources WHERE id=?', (resource_id,))
            return {'id':resource_id, 'deleted':True, 'removed_files':plan['files'], 'freed_bytes':plan['bytes']}

    def import_file(self, project_id, title, filename, data, resource_id=None, expected_version=None):
        from .ingestion import ingest, source_summary
        self.project(project_id)
        kind, metadata, files = ingest(filename, data)
        with PATH_LOCK:
            published = None
            library = self.library(project_id)
            try:
                with self.connection(project_id) as connection:
                    connection.execute('BEGIN IMMEDIATE')
                    if resource_id is None:
                        resource_id, version = uuid.uuid4().hex, 1
                    else:
                        existing = connection.execute('SELECT version FROM resources WHERE id=?', (resource_id,)).fetchone()
                        if existing is None:
                            raise KeyError('Source not found in this project')
                        if not self.source_available(project_id, resource_id):
                            raise StoreConflict('Nguồn đang xóa hoặc đã bị xóa')
                        if existing['version'] != expected_version:
                            raise StoreConflict('Nguồn đã thay đổi; tải lại trước khi thay file')
                        version = existing['version'] + 1
                    title = library.register({'id':resource_id, 'title':title.strip() or Path(metadata['filename']).stem})
                    row = {'id':resource_id, 'kind':kind, 'title':title, 'url':None, 'content':source_summary(metadata),
                           'status':metadata['status'], 'version':version, 'content_sha256':digest(canonical({'metadata':metadata,'title':title}))}
                    published = library.write_import(resource_id, version, {**files, 'source.md':library.document(row)})
                    self._write_resource(connection, row)
                    connection.execute('INSERT INTO source_ingestions VALUES(?,?,?)', (resource_id, version, canonical(metadata)))
                    reference = library.reference({**row, '_ingestion':metadata}, saving=True)
                return {**row, **reference}
            except BaseException:
                if published is not None:
                    library.discard_import(published)
                raise

    def ideas(self, project_id, include_deleted=False):
        with self.connection(project_id) as connection:
            result = []
            for row in connection.execute("SELECT * FROM ideas" + ('' if include_deleted else ' WHERE deleted_at IS NULL') + " ORDER BY rowid DESC"):
                item = dict(row)
                item["conversation"] = json.loads(item.pop("conversation_json"))
                variant = connection.execute('SELECT variant_json FROM variant_ideas WHERE idea_id=?', (item['id'],)).fetchone()
                item['variant'] = json.loads(variant['variant_json']) if variant else None
                if item['variant']:
                    parent = connection.execute('SELECT deleted_at FROM runs WHERE id=?',
                                                (item['variant']['parent_run_id'],)).fetchone()
                    item['variant']['parent_deleted_at'] = parent['deleted_at'] if parent else None
                result.append(item)
            return result

    def save_idea(self, project_id, text, title=None):
        if not text.strip():
            raise ValueError("Idea must contain text")
        idea_id = uuid.uuid4().hex
        title = idea_title(title) if title is not None else ''
        with self.connection(project_id) as connection:
            connection.execute("INSERT INTO ideas(id,text,conversation_json,state,error,created_at,title) VALUES(?,?,?,'DRAFT',NULL,?,?)",
                               (idea_id, text, "[]", datetime.now(timezone.utc).isoformat(), title))
        return next(item for item in self.ideas(project_id) if item["id"] == idea_id)

    @staticmethod
    def _variant_parent(connection, parent_run_id):
        row = connection.execute("SELECT runs.*,proposals.id AS parent_proposal_id,proposals.version AS parent_proposal_version,"
                                 "proposals.state AS proposal_state,proposals.body_json,proposals.context_snapshot_json,"
                                 "proposals.context_sha256 FROM runs JOIN proposals ON proposals.id=runs.proposal_id WHERE runs.id=?",
                                 (parent_run_id,)).fetchone()
        if row is None:
            raise KeyError('Run not found in this project')
        allowed = {'COMPLETED', 'FAILED', 'CANCELLED', 'REMOTE_SUCCEEDED', 'REMOTE_FAILED'}
        if row['deleted_at']:
            raise StoreConflict('Run cha đã bị ẩn; khôi phục run trước khi tạo biến thể')
        if row['state'] not in allowed:
            raise StoreConflict(f"Run cha chưa kết thúc hoặc cần đối soát ({row['state']}); chưa thể tạo biến thể")
        if row['proposal_state'] != 'APPROVED':
            raise StoreConflict('Run cha không có proposal đã duyệt')
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='working_runs'").fetchone():
            working = connection.execute('SELECT stop_confirmed FROM working_runs WHERE run_id=?', (parent_run_id,)).fetchone()
            if working is not None and not working['stop_confirmed']:
                raise StoreConflict('Working của run cha chưa xác nhận Kaggle đã dừng')
        return dict(row)

    def create_variant_idea(self, project_id, parent_run_id, request_id, title, purpose, change_summary,
                            captured_baseline, baseline_texts):
        """Create one DRAFT variant idea and pin its bounded baseline in the project database."""
        title = idea_title(title)
        purpose, change_summary = purpose.strip(), change_summary.strip()
        if not purpose or not change_summary or len(purpose) > 20_000 or len(change_summary) > 20_000:
            raise ValueError('Mục đích và thay đổi phải có nội dung (tối đa 20.000 ký tự mỗi ô)')
        if not re.fullmatch(r'[0-9a-f]{32}', request_id):
            raise ValueError('Invalid variant request ID')
        request_sha256 = digest(canonical({'parent_run_id': parent_run_id, 'title': title,
                                          'purpose': purpose, 'change_summary': change_summary}))
        captured_baseline = dict(captured_baseline)
        baseline_texts = dict(baseline_texts)
        with self.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute('SELECT idea_id,request_sha256 FROM variant_ideas WHERE request_id=?',
                                          (request_id,)).fetchone()
            if existing is not None:
                if existing['request_sha256'] != request_sha256:
                    raise StoreConflict('Request ID đã dùng cho parent hoặc nội dung biến thể khác')
                return self.idea(project_id, existing['idea_id'])

            parent = self._variant_parent(connection, parent_run_id)
            parent_snapshot = json.loads(parent['context_snapshot_json'])
            parent_body = json.loads(parent['body_json'])
            parent_sources = [
                {key: source[key] for key in ('id', 'title', 'kind', 'version', 'content_sha256')}
                for source in parent_snapshot['resources']
            ]
            expected_parent = {
                'run_id': parent_run_id, 'proposal_id': parent['parent_proposal_id'],
                'proposal_version': parent['parent_proposal_version'],
                'context_sha256': parent['context_sha256'], 'purpose': parent_body['objective'],
                'sources': parent_sources,
            }
            if captured_baseline.get('parent') != expected_parent:
                raise StoreConflict('Thông tin baseline cha đã đổi; tải lại run rồi tạo biến thể')
            files = captured_baseline.get('text_files')
            if not isinstance(files, list) or len(files) > 34:
                raise ValueError('Baseline text manifest không hợp lệ')
            total = 0
            available = set()
            for item in files:
                if not _valid_variant_stage(item) or type(item.get('available')) is not bool:
                    raise ValueError('Baseline path không nằm trong allowlist')
                if item.get('available') is True:
                    path = item['stage_path']
                    data = baseline_texts.get(path)
                    if not isinstance(data, str):
                        raise ValueError('Baseline text bị thiếu')
                    encoded = data.encode('utf-8')
                    total += len(encoded)
                    if total > 1_048_576 or len(encoded) != item.get('bytes') or digest(data) != item.get('sha256'):
                        raise StoreConflict('Baseline text vượt giới hạn hoặc SHA256 không khớp')
                    if path in available:
                        raise ValueError('Baseline text path bị lặp')
                    available.add(path)
            if set(baseline_texts) != available:
                raise ValueError('Baseline text không khớp manifest')

            idea_id = uuid.uuid4().hex
            created_at = datetime.now(timezone.utc).isoformat()
            variant = {
                'project_id': project_id, 'idea_id': idea_id, 'parent_run_id': parent_run_id,
                'parent_proposal_id': parent['parent_proposal_id'],
                'parent_proposal_version': parent['parent_proposal_version'],
                'purpose': purpose, 'change_summary': change_summary,
                'created_at': created_at, 'request_id': request_id,
                'baseline': captured_baseline,
            }
            idea_text = f'Mục đích mới: {purpose}\n\nThay đổi so với run gốc: {change_summary}'
            connection.execute("INSERT INTO ideas(id,text,conversation_json,state,error,created_at,title) VALUES(?,?,?,'DRAFT',NULL,?,?)",
                               (idea_id, idea_text, '[]', created_at, title))
            connection.execute('INSERT INTO variant_ideas VALUES(?,?,?,?,?,?,?,?,?,?)',
                               (idea_id, parent_run_id, parent['parent_proposal_id'], purpose, change_summary,
                                created_at, request_id, request_sha256, canonical(variant),
                                canonical(baseline_texts)))
        return self.idea(project_id, idea_id)

    def variant_stage_files(self, snapshot):
        """Return only verified, bounded text files pinned by a variant snapshot."""
        variant = snapshot.get('variant')
        if not variant:
            return {}
        idea_id = variant.get('idea_id')
        project_id = snapshot.get('project_id')
        with self.connection(project_id) as connection:
            row = connection.execute('SELECT variant_json,baseline_text_json FROM variant_ideas WHERE idea_id=?',
                                     (idea_id,)).fetchone()
        if row is None or json.loads(row['variant_json']) != variant:
            raise StoreConflict('Baseline biến thể đã bị đổi hoặc không còn khớp approval')
        texts = json.loads(row['baseline_text_json'])
        files = variant.get('baseline', {}).get('text_files')
        if not isinstance(files, list) or len(files) > 34:
            raise StoreConflict('Baseline manifest biến thể không hợp lệ')
        result = {}
        total = 0
        for item in files:
            if not _valid_variant_stage(item) or type(item.get('available')) is not bool:
                raise StoreConflict('Baseline path biến thể không nằm trong allowlist')
            if not item.get('available'):
                continue
            path = item['stage_path']
            content = texts.get(path)
            if not isinstance(content, str):
                raise StoreConflict('Baseline đã ghim bị thiếu; agent chưa được gọi')
            data = content.encode('utf-8')
            total += len(data)
            if (total > 1_048_576 or len(data) != item['bytes'] or digest(content) != item['sha256']):
                raise StoreConflict('Baseline đã ghim bị hỏng; agent chưa được gọi')
            result[path] = data
        if set(texts) != set(result):
            raise StoreConflict('Baseline đã ghim không khớp manifest; agent chưa được gọi')
        manifest = canonical({'variant': {key: value for key, value in variant.items() if key != 'baseline'},
                              'baseline': variant['baseline']}).encode('utf-8')
        result['baseline/manifest.json'] = manifest
        return result

    def context_snapshot(self, project_id, idea_id, resource_ids):
        if len(resource_ids) != len(set(resource_ids)):
            raise ValueError("Selected source IDs must be distinct")
        with self.connection(project_id) as connection:
            idea = connection.execute("SELECT id,text,conversation_json FROM ideas WHERE id=? AND deleted_at IS NULL", (idea_id,)).fetchone()
            if idea is None:
                raise KeyError("Idea not found in this project")
            resources = []
            for resource_id in resource_ids:
                row = connection.execute("SELECT * FROM resources WHERE id=? AND id NOT IN (SELECT resource_id FROM source_deletions)", (resource_id,)).fetchone()
                if row is None:
                    raise KeyError("Source not found in this project")
                resources.append(self.library(project_id).reference(dict(row)))
            context = {"project_id": project_id, "idea": {"id": idea["id"], "text": idea["text"],
                        "conversation": json.loads(idea["conversation_json"])},
                       "resources": sorted(resources, key=lambda item: item["id"])}
            variant = connection.execute('SELECT variant_json FROM variant_ideas WHERE idea_id=?', (idea_id,)).fetchone()
            if variant:
                context['variant'] = json.loads(variant['variant_json'])
            serialized = canonical(context)
            if len(serialized.encode("utf-8")) > 100_000:
                raise ValueError("Idea, conversation and source references exceed 100 KB")
            return {"snapshot": context, "context_sha256": digest(serialized)}

    def save_proposal(self, project_id, idea_id, body, context):
        snapshot = context["snapshot"]
        if snapshot["project_id"] != project_id or snapshot["idea"]["id"] != idea_id:
            raise ValueError("Context does not belong to this project/idea")
        serialized = canonical(snapshot)
        if digest(serialized) != context["context_sha256"]:
            raise ValueError("Context hash mismatch")
        self.library(project_id).agent_snapshot(snapshot)
        self.variant_stage_files(snapshot)
        proposal_id = uuid.uuid4().hex
        with self.connection(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._check_context(connection, snapshot)
            version = connection.execute("SELECT COALESCE(MAX(version),0)+1 FROM proposals WHERE idea_id=?",
                                         (idea_id,)).fetchone()[0]
            state = "NEEDS_CLARIFICATION" if body.get("needs_clarification") else "AWAITING_APPROVAL"
            connection.execute("UPDATE proposals SET state='STALE' WHERE idea_id=? AND state IN ('AWAITING_APPROVAL','NEEDS_CLARIFICATION')", (idea_id,))
            connection.execute("INSERT INTO proposals VALUES(?,?,?,?,?,?,?,NULL)",
                               (proposal_id, idea_id, version, canonical(body), serialized, context["context_sha256"], state))
            row = connection.execute("SELECT conversation_json FROM ideas WHERE id=?", (idea_id,)).fetchone()
            conversation = json.loads(row[0])
            conversation.append({"role": "assistant", "proposal_id": proposal_id, "version": version, "body": body})
            connection.execute("UPDATE ideas SET state=?,error=NULL,conversation_json=? WHERE id=?",
                               (state, canonical(conversation), idea_id))
        return proposal_id

    @staticmethod
    def _check_context(connection, snapshot):
        idea = connection.execute("SELECT text,conversation_json FROM ideas WHERE id=? AND deleted_at IS NULL", (snapshot["idea"]["id"],)).fetchone()
        # Assistant proposal messages do not change the human request context.
        human = lambda messages: [message for message in messages if message.get("role") == "user"]
        if idea is None or idea["text"] != snapshot["idea"]["text"] or human(json.loads(idea["conversation_json"])) != human(snapshot["idea"]["conversation"]):
            raise StoreConflict("Idea or answers changed; create a new proposal")
        variant = snapshot.get('variant')
        current_variant = connection.execute('SELECT variant_json FROM variant_ideas WHERE idea_id=?',
                                              (snapshot['idea']['id'],)).fetchone()
        if bool(variant) != bool(current_variant) or (variant and json.loads(current_variant['variant_json']) != variant):
            raise StoreConflict('Variant baseline or lineage changed; create a new proposal')
        for source in snapshot["resources"]:
            current = connection.execute("SELECT version,content_sha256 FROM resources WHERE id=? AND id NOT IN (SELECT resource_id FROM source_deletions)", (source["id"],)).fetchone()
            if current is None or current["version"] != source["version"] or current["content_sha256"] != source["content_sha256"]:
                raise StoreConflict("Source changed; create a new proposal")

    def idea(self, project_id, idea_id):
        item = next((item for item in self.ideas(project_id) if item["id"] == idea_id), None)
        if item is None:
            raise KeyError("Idea not found in this project")
        return item

    def reserve_plan(self, project_id, idea_id):
        with self.connection(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT state FROM ideas WHERE id=? AND deleted_at IS NULL", (idea_id,)).fetchone()
            if row is None:
                raise KeyError("Idea not found in this project")
            if row["state"] in {"PLANNING", "APPROVED"}:
                raise StoreConflict("Idea is planning or already approved; create a new idea for changed scope")
            connection.execute("UPDATE ideas SET state='PLANNING',error=NULL WHERE id=?", (idea_id,))

    def plan_failed(self, project_id, idea_id, error):
        with self.connection(project_id) as connection:
            connection.execute("UPDATE ideas SET state='FAILED',error=? WHERE id=? AND state='PLANNING'", (error[:1000], idea_id))

    def recover_planning(self):
        for project in self.list_projects():
            with self.connection(project["id"]) as connection:
                connection.execute("UPDATE ideas SET state='FAILED',error='Lập proposal bị gián đoạn khi backend khởi động lại. Trao đổi đã lưu vẫn còn; bấm tiếp tục để yêu cầu lượt mới.' WHERE state='PLANNING'")
                connection.execute("UPDATE ideas SET state='NEEDS_REVIEW' WHERE state IN ('AWAITING_APPROVAL','NEEDS_CLARIFICATION') AND "
                                   "(SELECT state FROM proposals WHERE idea_id=ideas.id ORDER BY version DESC LIMIT 1)='STALE'")

    def answer(self, project_id, idea_id, proposal_id, version, text):
        if not text.strip():
            raise ValueError("Answer must contain text")
        with self.connection(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            proposal = connection.execute("SELECT * FROM proposals WHERE id=? AND idea_id=?", (proposal_id, idea_id)).fetchone()
            if proposal is None:
                raise KeyError("Proposal not found in this project/idea")
            latest = connection.execute("SELECT MAX(version) FROM proposals WHERE idea_id=?", (idea_id,)).fetchone()[0]
            if proposal["version"] != version or version != latest or proposal["state"] != "NEEDS_CLARIFICATION":
                raise StoreConflict("Clarification is stale or not waiting for an answer")
            idea = connection.execute("SELECT state,conversation_json FROM ideas WHERE id=? AND deleted_at IS NULL", (idea_id,)).fetchone()
            if idea is None:
                raise StoreConflict('Khôi phục idea trước khi trả lời')
            if idea["state"] == "PLANNING":
                raise StoreConflict("Wait for the current planner")
            conversation = json.loads(idea["conversation_json"])
            conversation.append({"role": "user", "text": text, "reply_to": proposal_id})
            connection.execute("UPDATE ideas SET conversation_json=?,state='DRAFT',error=NULL WHERE id=?", (canonical(conversation), idea_id))
            connection.execute("UPDATE proposals SET state='STALE' WHERE idea_id=? AND state IN ('AWAITING_APPROVAL','NEEDS_CLARIFICATION')", (idea_id,))
        return self.idea(project_id, idea_id)

    def update_idea(self, project_id, idea_id, text, expected_text, title=None, expected_title=None):
        if not text.strip():
            raise ValueError("Idea must contain text")
        title = idea_title(title) if title is not None else None
        with self.connection(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT text,state,title FROM ideas WHERE id=? AND deleted_at IS NULL", (idea_id,)).fetchone()
            if row is None:
                raise KeyError("Idea not found in this project")
            if connection.execute('SELECT 1 FROM variant_ideas WHERE idea_id=?', (idea_id,)).fetchone():
                raise StoreConflict('Mục đích và thay đổi của idea biến thể đã được ghi nhận; tạo biến thể mới để đổi phạm vi')
            if row["text"] != expected_text or row["state"] in {"PLANNING", "APPROVED"}:
                raise StoreConflict("Idea changed, is planning, or was approved; reload or create a new idea")
            if title is not None and row['title'] != expected_title:
                raise StoreConflict('Tiêu đề đã thay đổi; tải lại idea trước khi lưu')
            if title is None or text != row['text']:
                connection.execute("UPDATE ideas SET text=?,conversation_json='[]',state='DRAFT',error=NULL WHERE id=?", (text, idea_id))
                connection.execute("UPDATE proposals SET state='STALE' WHERE idea_id=? AND state IN ('AWAITING_APPROVAL','NEEDS_CLARIFICATION')", (idea_id,))
            if title is not None:
                connection.execute('UPDATE ideas SET title=? WHERE id=?', (title, idea_id))
        return self.idea(project_id, idea_id)

    def rename_idea(self, project_id, idea_id, title, expected_title):
        title = idea_title(title)
        with self.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT title FROM ideas WHERE id=? AND deleted_at IS NULL', (idea_id,)).fetchone()
            if row is None:
                raise KeyError('Idea not found in this project')
            if row['title'] != expected_title:
                raise StoreConflict('Tiêu đề đã thay đổi; tải lại idea trước khi lưu')
            # Display metadata is independent of the approved request and its context hash.
            connection.execute('UPDATE ideas SET title=? WHERE id=?', (title, idea_id))
        return self.idea(project_id, idea_id)

    def proposals(self, project_id, idea_id=None):
        with self.connection(project_id) as connection:
            rows = connection.execute("SELECT * FROM proposals" + (" WHERE idea_id=?" if idea_id else "") + " ORDER BY rowid DESC", (idea_id,) if idea_id else ())
            result = []
            for row in rows:
                item = dict(row)
                item["body"] = json.loads(item.pop("body_json"))
                item["context_snapshot"] = json.loads(item.pop("context_snapshot_json"))
                result.append(item)
            return result

    def approve_proposal(self, project_id, proposal_id, version, context_sha256, idle_unknown_ids=()):
        from .models import WorkingProposal
        candidate = next((item for item in self.proposals(project_id) if item['id'] == proposal_id), None)
        with self.connection(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            proposal = connection.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
            if proposal is None:
                raise KeyError("Proposal not found in this project")
            if not connection.execute('SELECT 1 FROM ideas WHERE id=? AND deleted_at IS NULL', (proposal['idea_id'],)).fetchone():
                raise StoreConflict('Khôi phục idea trước khi duyệt proposal')
            if proposal["version"] != version or proposal["context_sha256"] != context_sha256:
                raise StoreConflict("Approval version/hash is stale")
            intent_key = proposal_id + ":" + str(version)
            existing = connection.execute("SELECT * FROM runs WHERE intent_key=?", (intent_key,)).fetchone()
            if existing is not None and proposal["state"] == "APPROVED":
                if existing['deleted_at']:
                    raise StoreConflict('Khôi phục run đã xóa trước khi tiếp tục')
                return dict(existing)
            latest = connection.execute("SELECT MAX(version) FROM proposals WHERE idea_id=?", (proposal["idea_id"],)).fetchone()[0]
            idea_state = connection.execute("SELECT state FROM ideas WHERE id=?", (proposal["idea_id"],)).fetchone()[0]
            if proposal["state"] != "AWAITING_APPROVAL" or latest != version or idea_state == "PLANNING":
                raise StoreConflict("Proposal is not current and awaiting approval")
            self._check_context(connection, json.loads(proposal["context_snapshot_json"]))
            # The exact pinned variant baseline must still be readable before approval.
            if candidate is not None:
                self.variant_stage_files(candidate['context_snapshot'])
            self.library(project_id).agent_snapshot(json.loads(proposal['context_snapshot_json']))
            body = WorkingProposal.model_validate_json(proposal["body_json"])
            snapshot = json.loads(proposal["context_snapshot_json"])
            sources = {source["id"]: source for source in snapshot["resources"]}
            if any(ref not in sources for ref in body.data_refs):
                raise StoreConflict("Proposal cites unselected source IDs")
            candidates = connection.execute("SELECT id,state FROM runs WHERE deleted_at IS NULL AND state NOT IN ('COMPLETED','FAILED','CANCELLED','REMOTE_SUCCEEDED','REMOTE_FAILED','COLLECTING')").fetchall()
            blocking = next((row for row in candidates if not (row['state'] == 'UNKNOWN' and row['id'] in idle_unknown_ids)), None)
            if blocking:
                raise StoreConflict(f"Run {blocking['id'][:8]} ({blocking['state']}) đang chặn lượt mới. Run đã kết thúc trên Kaggle không chặn duyệt proposal.")
            run_id = uuid.uuid4().hex
            artifact_dir = "runs/" + run_id
            connection.execute("INSERT INTO runs(id,proposal_id,state,intent_key,artifact_dir) VALUES(?,?,'APPROVED',?,?)",
                               (run_id, proposal_id, intent_key, artifact_dir))
            connection.execute("UPDATE proposals SET state='APPROVED',approved_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), proposal_id))
            connection.execute("UPDATE ideas SET state='APPROVED' WHERE id=?", (proposal["idea_id"],))
            return dict(connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())

    def approved_context(self, project_id, run_id):
        # The future coder must use this gate, never a client-supplied proposal body.
        with self.connection(project_id) as connection:
            row = connection.execute("SELECT runs.state,proposals.state AS proposal_state,proposals.body_json,proposals.context_snapshot_json,proposals.context_sha256 FROM runs JOIN proposals ON proposals.id=runs.proposal_id WHERE runs.id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError("Run not found in this project")
            if row["proposal_state"] != "APPROVED" or row["state"] != "APPROVED":
                raise StoreConflict("Implementation requires an approved run")
            return {"body": json.loads(row["body_json"]), "snapshot": json.loads(row["context_snapshot_json"]), "context_sha256": row["context_sha256"]}

    def history(self, project_id, include_deleted=False):
        with self.connection(project_id) as connection:
            return {"proposals": [dict(row) for row in connection.execute(
                "SELECT id,idea_id,version,state,context_sha256,approved_at FROM proposals ORDER BY rowid DESC")],
                "runs": [dict(row) for row in connection.execute(
                "SELECT id,proposal_id,node_id,state,artifact_dir,error,report_path,deleted_at FROM runs" + ('' if include_deleted else ' WHERE deleted_at IS NULL') + " ORDER BY rowid DESC")]}

    @staticmethod
    def _can_delete_run(connection, run):
        if run['state'] not in {'APPROVED', 'PREFLIGHT', 'FAILED', 'CANCELLED', 'COMPLETED', 'REMOTE_SUCCEEDED', 'REMOTE_FAILED'}:
            return False
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='working_runs'").fetchone():
            working = connection.execute('SELECT stop_confirmed FROM working_runs WHERE run_id=?', (run['id'],)).fetchone()
            if working is not None:
                return bool(working['stop_confirmed'])
        identity = json.loads(run['identity_json']) if run['identity_json'] else None
        return not identity or str(identity.get('status', '')).lower() in {'complete', 'completed', 'error', 'cancelled', 'canceled'}

    def can_delete_run(self, project_id, run_id):
        with self.connection(project_id) as connection:
            row = connection.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if row is None:
                raise KeyError('Run not found in this project')
            return self._can_delete_run(connection, row)

    def set_deleted(self, project_id, kind, item_id, deleted=True):
        if kind not in {'ideas', 'runs'}:
            raise ValueError('Unknown item type')
        with self.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute(f'SELECT * FROM {kind} WHERE id=?', (item_id,)).fetchone()
            if row is None:
                raise KeyError('Item not found in this project')
            if deleted and kind == 'ideas':
                if row['state'] == 'PLANNING':
                    raise StoreConflict('Chờ Codex lập proposal xong trước khi xóa idea')
                runs = connection.execute('SELECT runs.* FROM runs JOIN proposals ON proposals.id=runs.proposal_id WHERE proposals.idea_id=? AND runs.deleted_at IS NULL', (item_id,))
                if any(not self._can_delete_run(connection, run) for run in runs):
                    raise StoreConflict('Dừng hoặc đối soát run của idea trước khi xóa')
            if deleted and kind == 'runs' and not self._can_delete_run(connection, row):
                raise StoreConflict('Run đang hoạt động hoặc chưa xác nhận Kaggle dừng; chưa thể xóa')
            timestamp = (row['deleted_at'] or datetime.now(timezone.utc).isoformat()) if deleted else None
            connection.execute(f'UPDATE {kind} SET deleted_at=? WHERE id=?', (timestamp, item_id))
            return {'id': item_id, 'deleted_at': timestamp}

    def run(self, project_id, run_id):
        with self.connection(project_id) as connection:
            row = connection.execute('SELECT runs.*, proposals.version AS proposal_version FROM runs JOIN proposals ON proposals.id=runs.proposal_id WHERE runs.id=?', (run_id,)).fetchone()
            if row is None:
                raise KeyError('Run not found in this project')
            item = dict(row)
            item['can_delete'] = self._can_delete_run(connection, row)
            retry = connection.execute('SELECT parent_run_id FROM run_retries WHERE run_id=?', (run_id,)).fetchone()
            item['parent_run_id'] = retry['parent_run_id'] if retry else None
            attempts = [dict(a) for a in connection.execute('SELECT * FROM implementation_attempts WHERE run_id=? ORDER BY attempt', (run_id,))]
            for attempt in attempts:
                attempt['node'] = json.loads(attempt.pop('node_json')) if attempt['node_json'] else None
                attempt['checks'] = json.loads(attempt.pop('checks_json')) if attempt['checks_json'] else None
            item['attempts'] = attempts
            return item

    def implementation_snapshot(self, project_id, run_id, *, read_only=False):
        """Compatibility access for saved notebook runs and standalone legacy tools."""
        approved = self.approved_snapshot(project_id, run_id)
        if not read_only and self.run(project_id, run_id)['state'] not in {'APPROVED', 'FAILED', 'IMPLEMENTING', 'PREFLIGHT'}:
            raise StoreConflict('Implementation requires an approved proposal and eligible run')
        return approved

    def approved_snapshot(self, project_id, run_id):
        """Read the exact approved request without workload-format requirements."""
        with self.connection(project_id) as connection:
            row = connection.execute('SELECT runs.state,proposals.state AS proposal_state,proposals.body_json,proposals.context_snapshot_json,proposals.context_sha256 FROM runs JOIN proposals ON proposals.id=runs.proposal_id WHERE runs.id=?', (run_id,)).fetchone()
            if row is None:
                raise KeyError('Run not found in this project')
            if row['proposal_state'] != 'APPROVED':
                raise StoreConflict('Working requires an approved proposal')
            snapshot = json.loads(row['context_snapshot_json'])
            if digest(canonical(snapshot)) != row['context_sha256']:
                raise StoreConflict('Pinned context hash mismatch')
            return {'body': json.loads(row['body_json']), 'snapshot': snapshot, 'context_sha256': row['context_sha256']}

    def reserve_submission(self, project_id, run_id, intent):
        with self.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if row is None:
                raise KeyError('Run not found in this project')
            if row['identity_json']:
                return False
            approved = connection.execute('SELECT state FROM proposals WHERE id=?', (row['proposal_id'],)).fetchone()
            if row['state'] != 'PREFLIGHT' or approved['state'] != 'APPROVED' or row['code_sha256'] != intent['code_sha256']:
                raise StoreConflict('Submission requires the exact approved preflight bundle')
            connection.execute("UPDATE runs SET state='SUBMITTING',identity_json=?,error=NULL WHERE id=?", (canonical(intent), run_id))
            return True

    def submission_observed(self, project_id, run_id, state, identity, error=None):
        with self.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT identity_json,state FROM runs WHERE id=?', (run_id,)).fetchone()
            if row is None or not row['identity_json']:
                raise StoreConflict('No durable submission intent')
            previous = json.loads(row['identity_json'])
            # Intent and resolved identifiers are immutable once recorded.
            for key in ('account','username','kernel_ref','notebook_sha256','submitted_source_sha256','code_sha256','context_sha256','version','kernel_id','script_version_id','session_id'):
                if previous.get(key) is not None and identity.get(key) != previous[key]:
                    raise StoreConflict('Pinned submission identity mismatch: ' + key)
            # A later monitoring/reconcile read cannot undo locally collected results.
            if row['state']=='COMPLETED':return 'COMPLETED'
            connection.execute('UPDATE runs SET state=?,identity_json=?,error=? WHERE id=?', (state, canonical(identity), error, run_id))
            return state

    def collection_failed(self, project_id, run_id, error_type):
        """Keep a remote success in COLLECTING until outputs and report are durable."""
        if error_type not in {'ValueError','ValidationError','RuntimeError','TimeoutError','OSError','KeyError','TypeError'}:
            error_type='Error'
        with self.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            row=connection.execute('SELECT state,identity_json FROM runs WHERE id=?',(run_id,)).fetchone()
            if row is None:
                raise KeyError('Run not found in this project')
            if row['state']=='COMPLETED':
                return 'COMPLETED'
            if row['state'] not in {'COLLECTING','REMOTE_SUCCEEDED'} or not row['identity_json']:
                return row['state']
            message=f'Exact Kaggle success is still awaiting validated outputs/report ({error_type}); no resubmit was performed.'
            connection.execute('UPDATE runs SET error=? WHERE id=?',(message,run_id))
            return row['state']

    def complete_collected_run(self, project_id, run_id, identity, node_id, node, report_path):
        """Atomically expose COMPLETED only after files and the report were persisted."""
        if report_path != 'report.md':
            raise ValueError('Run report path must be the validated report artifact')
        with self.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            row=connection.execute('SELECT state,identity_json FROM runs WHERE id=?',(run_id,)).fetchone()
            if row is None:
                raise KeyError('Run not found in this project')
            if row['state']=='COMPLETED':
                if connection.execute('SELECT report_path FROM runs WHERE id=?',(run_id,)).fetchone()[0] != report_path:
                    raise StoreConflict('Completed run report path changed')
                return 'COMPLETED'
            if row['state'] not in {'COLLECTING','REMOTE_SUCCEEDED'} or not row['identity_json']:
                raise StoreConflict('Validated output collection requires a terminal-success run')
            previous=json.loads(row['identity_json'])
            for key in ('account','username','kernel_ref','version','kernel_id','script_version_id','session_id',
                        'code_sha256','context_sha256'):
                if previous.get(key) is not None and identity.get(key)!=previous[key]:
                    raise StoreConflict('Pinned collection identity mismatch: '+key)
            connection.execute('UPDATE runs SET state=\'COMPLETED\',node_id=?,node_json=?,identity_json=?,report_path=?,error=NULL WHERE id=?',
                               (node_id,canonical(node),canonical(identity),report_path,run_id))
            return 'COMPLETED'

    def recover_submission(self):
        for project in self.list_projects():
            with self.connection(project['id']) as connection:
                connection.execute("UPDATE runs SET state='UNKNOWN',error='Submission interrupted by restart; reconcile using read-only history, never push again' WHERE state='SUBMITTING'")

    def reserve_retry(self, project_id, parent_run_id, request_id, idle_unknown_ids=()):
        """A deliberate new execution shares approval, never the old remote identity."""
        if not re.fullmatch(r'[0-9a-f]{32}', request_id):
            raise ValueError('Invalid retry request ID')
        with self.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute('SELECT run_id,parent_run_id FROM run_retries WHERE request_id=?', (request_id,)).fetchone()
            if existing:
                if existing['parent_run_id'] != parent_run_id:
                    raise StoreConflict('Retry request belongs to a different run')
                return dict(connection.execute('SELECT * FROM runs WHERE id=?', (existing['run_id'],)).fetchone()), False
            parent = connection.execute('SELECT runs.*,proposals.state AS proposal_state FROM runs JOIN proposals ON proposals.id=runs.proposal_id WHERE runs.id=?', (parent_run_id,)).fetchone()
            if parent is None:
                raise KeyError('Run not found in this project')
            if parent['deleted_at']:
                raise StoreConflict('Khôi phục run trước khi tạo lượt mới')
            eligible = {'FAILED', 'CANCELLED', 'REMOTE_FAILED', 'REMOTE_SUCCEEDED', 'COLLECTING', 'COMPLETED'}
            if parent_run_id in idle_unknown_ids:
                eligible.add('UNKNOWN')
            if parent['proposal_state'] != 'APPROVED' or parent['state'] not in eligible:
                raise StoreConflict('Chỉ tạo lượt mới sau khi lượt cũ kết thúc hoặc Kaggle xác nhận account đang rảnh')
            candidates = connection.execute("SELECT id,state FROM runs WHERE deleted_at IS NULL AND state NOT IN ('FAILED','CANCELLED','REMOTE_FAILED','REMOTE_SUCCEEDED','COLLECTING','COMPLETED')").fetchall()
            if any(row['state'] != 'UNKNOWN' or row['id'] not in idle_unknown_ids for row in candidates):
                raise StoreConflict('Một run khác đang hoạt động; hoàn tất run đó trước khi tạo lượt mới')
            run_id = uuid.uuid4().hex
            connection.execute("INSERT INTO runs(id,proposal_id,state,intent_key,artifact_dir) VALUES(?,?,'APPROVED',?,?)",
                               (run_id, parent['proposal_id'], 'retry:' + request_id, 'runs/' + run_id))
            connection.execute('INSERT INTO run_retries VALUES(?,?,?)', (run_id, parent_run_id, request_id))
            return dict(connection.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()), True

    def retry_run(self, project_id, parent_run_id, request_id):
        with self.connection(project_id) as connection:
            row = connection.execute('SELECT run_id,parent_run_id FROM run_retries WHERE request_id=?', (request_id,)).fetchone()
            if row is None:
                return None
            if row['parent_run_id'] != parent_run_id:
                raise StoreConflict('Retry request belongs to a different run')
            return row['run_id']

    def retry_feedback(self, project_id, run_id):
        with self.connection(project_id) as connection:
            rows = connection.execute('SELECT text FROM logs WHERE run_id=? AND generation=(SELECT MAX(generation) FROM logs WHERE run_id=?) ORDER BY seq DESC LIMIT 20', (run_id, run_id)).fetchall()
            return '\n'.join(row['text'] for row in reversed(rows))[-16000:]

    def reserve_implementation(self, project_id, run_id, request_id, *, repair=False, origin='CODEX'):
        if origin not in {'CODEX', 'REUSE'}:
            raise ValueError('Invalid implementation origin')
        with self.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT runs.state,runs.identity_json,proposals.state AS proposal_state FROM runs JOIN proposals ON proposals.id=runs.proposal_id WHERE runs.id=?', (run_id,)).fetchone()
            if row is None:
                raise KeyError('Run not found in this project')
            states = {'IMPLEMENTING'} if repair else {'APPROVED', 'FAILED', 'PREFLIGHT'}
            if row['proposal_state'] != 'APPROVED' or row['state'] not in states or row['identity_json']:
                raise StoreConflict('Run is not eligible for a coder call')
            attempts = connection.execute('SELECT attempt,state,checks_json FROM implementation_attempts WHERE run_id=? ORDER BY attempt', (run_id,)).fetchall()
            if any(a['state'] == 'RUNNING' for a in attempts):
                raise StoreConflict('A coder request is already active')
            attempt = len(attempts) + 1
            connection.execute("INSERT INTO implementation_attempts(run_id,attempt,request_id,state,origin) VALUES(?,?,?,'RUNNING',?)", (run_id, attempt, request_id, origin))
            connection.execute("UPDATE runs SET state='IMPLEMENTING',error=NULL WHERE id=?", (run_id,))
            return attempt

    def finish_implementation_attempt(self, project_id, run_id, attempt, node, checks, session_id=None, error=None):
        with self.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            cursor = connection.execute("UPDATE implementation_attempts SET state=?,node_json=?,checks_json=?,session_id=?,error=? WHERE run_id=? AND attempt=? AND state='RUNNING'",
                                       ('COMPLETE' if checks and checks['pass'] else 'FAILED', canonical(node) if node else None,
                                        canonical(checks) if checks else None, session_id, error, run_id, attempt))
            if cursor.rowcount != 1:
                raise StoreConflict('Coder attempt is no longer current')
            if node:
                connection.execute('UPDATE runs SET node_id=?,node_json=?,code_sha256=? WHERE id=?',
                                   (node['id'], canonical(node), checks['code_sha256'] if checks else None, run_id))
            if checks and checks['pass']:
                connection.execute("UPDATE runs SET state='PREFLIGHT',error=NULL WHERE id=?", (run_id,))

    def implementation_failed(self, project_id, run_id, error):
        with self.connection(project_id) as connection:
            connection.execute("UPDATE runs SET state='FAILED',error=? WHERE id=? AND state IN ('APPROVED','IMPLEMENTING','PREFLIGHT')", (error[:1000], run_id))

    def recover_implementation(self):
        for project in self.list_projects():
            with self.connection(project['id']) as connection:
                connection.execute("UPDATE implementation_attempts SET state='FAILED',error='Interrupted by restart; request remains in history' WHERE state='RUNNING'")
                connection.execute("UPDATE runs SET state='FAILED',error='Implementation interrupted by restart; request another code revision explicitly' WHERE state='IMPLEMENTING'")

    def record_preflight_review(self, project_id, run_id, checks, node):
        # Rechecking saved source consumes no additional coder call and never changes scope.
        with self.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            run = connection.execute('SELECT state,code_sha256 FROM runs WHERE id=?', (run_id,)).fetchone()
            if run is None:
                raise KeyError('Run not found in this project')
            if run['state'] not in {'PREFLIGHT', 'FAILED'} or checks['code_sha256'] != run['code_sha256']:
                raise StoreConflict('Only the exact saved implementation can be reviewed before submission')
            attempt = connection.execute('SELECT MAX(attempt) FROM implementation_attempts WHERE run_id=?', (run_id,)).fetchone()[0]
            error = None if checks['pass'] else '; '.join(checks['errors'])[:1000]
            connection.execute('UPDATE implementation_attempts SET state=?,checks_json=?,node_json=?,error=? WHERE run_id=? AND attempt=?',
                               ('COMPLETE' if checks['pass'] else 'FAILED', canonical(checks), canonical(node), error, run_id, attempt))
            connection.execute('UPDATE runs SET state=?,error=?,node_id=?,node_json=? WHERE id=?',
                               ('PREFLIGHT' if checks['pass'] else 'FAILED', error, node['id'], canonical(node), run_id))
