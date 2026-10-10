"""Immutable public benchmarks and the references frozen into run approvals."""
import hashlib
import json
import posixpath
import re

from pydantic import Field, field_validator

from .models import StrictModel, ProposalMetric
from .store import StoreConflict, canonical


class BenchmarkDefinition(StrictModel):
    metric: ProposalMetric
    test_split: str = Field(min_length=1, max_length=20_000)
    train_split: str | None = Field(default=None, max_length=20_000)

    @field_validator('metric')
    @classmethod
    def valid_metric(cls, value):
        name, definition = value.name.strip(), value.definition.strip()
        if (not name or len(name) > 100 or not re.fullmatch(r'[/\w.\- ]+', name)
                or name.startswith('/') or posixpath.normpath(name) != name or name in {'.', '..'}):
            raise ValueError('Metric name must be a valid MLflow key (at most 100 characters)')
        if not definition or len(definition) > 20_000:
            raise ValueError('Metric definition must contain text (at most 20,000 characters)')
        return ProposalMetric(name=name, direction=value.direction, definition=definition)

    @field_validator('test_split', 'train_split')
    @classmethod
    def nonblank(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError('Split description must not be blank')
        return value


SCHEMA = '''CREATE TABLE IF NOT EXISTS benchmarks(
id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE REFERENCES runs(id),
title TEXT NOT NULL, definition_json TEXT NOT NULL, receipt_json TEXT NOT NULL);
'''


class BenchmarkCatalog:
    def __init__(self, store):
        self.store = store

    def list(self, project_id):
        with self.store.connection(project_id) as connection:
            connection.executescript(SCHEMA)
            rows = connection.execute('SELECT benchmarks.* FROM benchmarks JOIN runs ON runs.id=benchmarks.run_id '
                                      "WHERE runs.state='COMPLETED' AND runs.deleted_at IS NULL ORDER BY benchmarks.rowid DESC")
            return [self._decode(row) for row in rows]

    @staticmethod
    def _decode(row):
        value = dict(row)
        value['definition'] = json.loads(value.pop('definition_json'))
        value['dataset'] = json.loads(value.pop('receipt_json'))
        return value

    def require(self, project_id, benchmark_id):
        value = next((item for item in self.list(project_id) if item['id'] == benchmark_id), None)
        if value is None:
            raise StoreConflict('Chọn benchmark đã hoàn tất, dataset public đã xác minh trong project này.')
        return value

    def save(self, project_id, run_id, title, definition, receipt):
        definition = BenchmarkDefinition.model_validate(definition).model_dump()
        handle = receipt.get('handle', '')
        if (not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+', handle)
                or receipt.get('visibility') != 'public'
                or type(receipt.get('version')) is not int or receipt['version'] < 1
                or receipt.get('url') != 'https://www.kaggle.com/datasets/' + handle
                or not re.fullmatch(r'[0-9a-f]{64}', receipt.get('manifest_sha256', ''))):
            raise ValueError('Benchmark requires a verified public dataset receipt')
        with self.store.connection(project_id) as connection:
            connection.executescript(SCHEMA)
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute('SELECT * FROM benchmarks WHERE run_id=?', (run_id,)).fetchone()
            if existing:
                if json.loads(existing['receipt_json']) != receipt or json.loads(existing['definition_json']) != definition:
                    raise StoreConflict('Benchmark đã đóng băng; tạo benchmark mới để thay đổi.')
                return self._decode(existing)
            connection.execute('INSERT INTO benchmarks VALUES(?,?,?,?,?)',
                               (run_id, run_id, title, canonical(definition), canonical(receipt)))
            return self._decode(connection.execute('SELECT * FROM benchmarks WHERE id=?', (run_id,)).fetchone())


def approval_benchmark(snapshot):
    return snapshot['idea'].get('benchmark')


def validate_benchmark_output(root, definition, manifest):
    """Check package paths and bytes before handing the directory to KaggleHub."""
    definition = BenchmarkDefinition.model_validate(definition).model_dump()
    files = {item['path']: item for item in manifest['files']}
    package = root / 'output/benchmark'
    config = json.loads((package / 'benchmark.json').read_text(encoding='utf-8'))
    if config.get('schema_version') != 1 or config.get('definition') != definition:
        raise ValueError('Benchmark package differs from the approved definition')
    test_files = config.get('test_files')
    train_files = config.get('train_files', [])
    if not isinstance(test_files, list) or not test_files or not isinstance(train_files, list):
        raise ValueError('Benchmark needs test files; train files are optional')
    if definition['train_split'] and not train_files:
        raise ValueError('Approved train split has no files')
    if not definition['train_split'] and train_files:
        raise ValueError('Train files were not requested')
    interface = config.get('evaluator_interface')
    if isinstance(interface, str):
        valid_interface = bool(interface.strip())
    elif isinstance(interface, dict):
        valid_interface = all(isinstance(interface.get(name), str) and interface[name].strip()
                              for name in ('function', 'cli'))
        valid_interface = valid_interface and all(isinstance(name, str) for name in interface)
    else:
        valid_interface = False
    if not valid_interface:
        raise ValueError('Benchmark must describe the evaluator interface')
    selected = ['benchmark.json', 'evaluate.py', *test_files, *train_files]
    if len(set(selected)) != len(selected):
        raise ValueError('Benchmark files must be distinct')
    for name in selected:
        if (not isinstance(name, str) or not name or name.startswith('/') or '\\' in name
                or '..' in name.split('/') or not (package / name).is_file()
                or not (package / name).resolve().is_relative_to(package.resolve())
                or 'output/benchmark/' + name not in files):
            raise ValueError('Benchmark manifest contains an invalid or uncollected file')
    actual = {path.relative_to(package).as_posix() for path in package.rglob('*') if path.is_file()}
    if actual != set(selected):
        raise ValueError('Benchmark package contains undeclared files')
    # Upload exactly the collected package, not agent workspace or credentials.
    package_files = sorted((item for name, item in files.items() if name.startswith('output/benchmark/')), key=lambda item: item['path'])
    for item in package_files:
        path = root / item['path']
        if path.is_symlink() or path.stat().st_size != item['bytes']:
            raise ValueError('Benchmark file changed after collection')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != item['sha256']:
                raise ValueError('Benchmark file hash changed after collection')
    return package, hashlib.sha256(canonical(package_files).encode()).hexdigest()


def validate_selection(store, project_id, mode, benchmark_id=None, definition=None):
    if mode == 'benchmark':
        if benchmark_id:
            raise ValueError('A new benchmark cannot select an existing benchmark')
        return None, BenchmarkDefinition.model_validate(definition).model_dump()
    if definition is not None:
        raise ValueError('Benchmark definition belongs only to Tạo benchmark mới')
    if mode == 'training_research' and benchmark_id:
        BenchmarkCatalog(store).require(project_id, benchmark_id)
    elif mode != 'training_research' and benchmark_id:
        raise ValueError('Only Training/Research selects a benchmark')
    return benchmark_id, None
