"""Read editable system prompts by alias, without caching their contents."""
import json
from pathlib import Path
import re

_ROOT = Path(__file__).resolve().parent


def load_prompt(alias, **values):
    aliases = json.loads((_ROOT / 'aliases.json').read_text(encoding='utf-8-sig'))
    if not isinstance(aliases, dict):
        raise ValueError('System prompt aliases must be a JSON object')
    if alias not in aliases:
        raise ValueError(f'Unknown system prompt alias: {alias}')
    filename = aliases[alias]
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError(f'Invalid system prompt filename for alias: {alias}')
    path = (_ROOT / filename).resolve()
    if not path.is_relative_to(_ROOT.resolve()):
        raise ValueError(f'System prompt file must stay inside system_prompt: {alias}')
    try:
        text = path.read_text(encoding='utf-8-sig').rstrip('\n')
    except FileNotFoundError as exc:
        raise FileNotFoundError(f'System prompt file missing for alias {alias}: {filename}') from exc
    if not text.strip():
        raise ValueError(f'System prompt is empty: {alias}')

    def substitute(match):
        name = match.group(1)
        if name not in values:
            raise ValueError(f'Missing variable {name} for system prompt {alias}')
        return str(values[name])

    return re.sub(r'\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}', substitute, text)

