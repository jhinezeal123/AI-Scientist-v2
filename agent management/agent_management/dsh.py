"""Import installed DSH provider configuration into private packaged profiles."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import yaml

from .models import HarnessSpec


class InertLoader(yaml.SafeLoader):
    pass


InertLoader.add_constructor('tag:yaml.org,2002:js', lambda loader, node: '<expression>')


def install_local_profile(repository: Path, *, home=None, entrypoint=None):
    home = Path(home or Path.home() / '.dsh')
    if entrypoint is None:
        cache = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.cache')) / 'npm-cache/_npx'
        candidates = list(cache.glob('*/node_modules/@deepseek-ai/dsh/lib/bin.js'))
        candidates.sort(key=lambda p: (json.loads((p.parent.parent / 'package.json').read_text()).get('version') != '0.2.0-rc.2', str(p)))
        entrypoint = next(iter(candidates), None)
    node = shutil.which('node')
    if not node or not entrypoint or not Path(entrypoint).is_file():
        raise ValueError('Install DSH and Node first. This action never downloads a runtime.')
    source = home / 'profiles/web/cordis.patch.yml'
    document = yaml.compose(source.read_text(encoding='utf-8'))
    selected = []
    for entry in document.value:
        pairs = {k.value:v for k,v in entry.value}
        if pairs.get('id') and pairs['id'].value in {'llm-pi-ai', 'agent-default-model'}:
            selected.append(entry)
    overlay = yaml.serialize(yaml.SequenceNode('tag:yaml.org,2002:seq', selected))
    metadata = yaml.load(overlay, Loader=InertLoader)
    default = next((e.get('config', {}) for e in metadata if e['id']=='agent-default-model'), {})
    if not default.get('provider') or not default.get('model'):
        raise ValueError('Select a provider/model in the existing DSH Web profile first')
    template = repository / '.workbench/agents/providers/dsh'
    if any(p.is_symlink() for p in [template, *template.parents] if p != repository.parent):
        raise ValueError('Provider storage must not be redirected')
    template.mkdir(parents=True, exist_ok=True)
    profile = template / 'profiles/acp'
    profile.mkdir(parents=True, exist_ok=True)
    for name in ('package.json','cordis.yml'):
        shutil.copyfile(home / 'profiles/acp' / name, profile / name)
    # JSON-only edits are applied by Workspaces. DSH receives no model-callable tools,
    # implicit skill discovery, subagents, plugin installation or user/global patches.
    base = Path(entrypoint).parents[2] / 'dsh-base/cordis.patch.yml'
    base_rows = yaml.load(base.read_text(encoding='utf-8'), Loader=InertLoader)[0]['insert']
    disabled = [{'id':r['id'], 'disabled':True} for r in base_rows
        if r['id'].startswith('tool-') or r['id'] in {'plugin-manager','config-editor','hmr','skill-filesystem','agent-instructions','session-title-llm','subagent-spawn-in-process','subagent-fork-in-process'}]
    (profile / 'cordis.patch.yml').write_text(overlay + yaml.safe_dump(disabled), encoding='utf-8')
    credentials = yaml.safe_load((home / '.credentials.yaml').read_text(encoding='utf-8'))
    refs = {k:v for k,v in credentials.get('refs',{}).items() if k in overlay}
    if not refs:
        raise ValueError('Selected DSH provider has no saved credential reference')
    credential_file = template / '.credentials.yaml'
    credential_file.write_text(yaml.safe_dump({'version':1,'refs':refs}), encoding='utf-8')
    if os.name != 'nt':
        credential_file.chmod(0o600)
    return HarnessSpec(id='dsh', kind='acp', executable=node,
        args=[str(Path(entrypoint).resolve()), '--profile', 'acp'], managed_home=str(template),
        models=[json.dumps([default['provider'],default['model']], separators=(',',':'))])


def session_home(template: Path, workspace: Path):
    template = template.resolve(strict=True)
    key = hashlib.sha256(str(workspace.resolve()).encode()).hexdigest()
    # Keep live state separate from provider templates denied to other sandboxes.
    target = template.parents[1] / 'runtimes' / ('dsh-' + key)
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError('Refusing redirected DSH session storage')
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template / 'profiles', target / 'profiles', dirs_exist_ok=True)
    destination = target / '.credentials.yaml'
    shutil.copyfile(template / '.credentials.yaml', destination)
    if os.name != 'nt':
        destination.chmod(0o600)
    return target
