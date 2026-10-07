"""Resolve the configured CLI again after desktop app upgrades move its binary."""
import os
from pathlib import Path
import shutil


def resolve_codex_executable(configured):
    path = Path(configured)
    if path.is_file() and (os.name != 'nt' or path.suffix.lower() == '.exe'):
        return path
    discovered = shutil.which('codex.exe' if os.name == 'nt' else 'codex')
    if discovered and Path(discovered).is_file():
        return Path(discovered)
    if os.name == 'nt':
        root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'OpenAI/Codex/bin'
        candidates = list(root.glob('*/codex.exe'))
        if candidates:
            return max(candidates, key=lambda candidate: candidate.stat().st_mtime)
    if path.is_file():
        return path
    raise ValueError('Codex CLI executable is unavailable; install/configure Codex before Working')
