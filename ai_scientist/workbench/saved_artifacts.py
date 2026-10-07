"""Read saved artifacts and collection metadata without loading execution services."""
import hashlib
import json
from pathlib import Path, PurePosixPath

MAX_OUTPUT_BYTES = 10_000_000
MAX_REPORT_ATTEMPTS = 3

def _collection_state(path: Path) -> dict:
    try:
        value = _read_json(path, 20_000)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}

def _report_limit(state: dict) -> int:
    """Default budget; a user-authorized repair can persist a larger limit for one run."""
    limit = state.get('report_limit', MAX_REPORT_ATTEMPTS)
    if type(limit) is not int or not MAX_REPORT_ATTEMPTS <= limit <= 100:
        raise ValueError('Invalid authorized report attempt limit')
    return limit

def _read_json(path: Path, limit=MAX_OUTPUT_BYTES):
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(path.parent.resolve()):
        raise ValueError('Required collected evidence file is missing or linked')
    if path.stat().st_size > limit:
        raise ValueError('Collected evidence exceeds its read limit')
    return json.loads(path.read_text(encoding='utf-8'))

def _safe_output_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError('Unsafe output manifest path')
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or parsed.parts[0] != 'output' or any(part in {'', '.', '..'} for part in parsed.parts):
        raise ValueError('Unsafe output manifest path')
    path = root.joinpath(*parsed.parts)
    current = root
    for part in parsed.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Linked collected output refused')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Output manifest path escapes run root')
    return path

def artifact_paths(root: Path) -> list[str]:
    manifest_path = root / 'collection-manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file():
        return []
    try:
        saved = _read_json(manifest_path, 100_000)
        files = saved['manifest']
        if not isinstance(files, list):
            return []
        result = []
        for item in files:
            path = _safe_output_path(root, item['path'])
            if (path.is_file() and path.stat().st_size == item['bytes']
                    and hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']):
                result.append(item['path'])
        return result
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return []
