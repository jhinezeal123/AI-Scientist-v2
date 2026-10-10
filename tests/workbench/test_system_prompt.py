import asyncio
import json

import pytest

from ai_scientist.workbench import system_prompt
from test_working import fixture as working_fixture


@pytest.fixture
def prompt_root(tmp_path, monkeypatch):
    root = tmp_path / 'prompts'
    root.mkdir()
    aliases = {'working.agent': 'agent.md', 'working.instructions': 'instructions.md'}
    (root / 'aliases.json').write_text(json.dumps(aliases), encoding='utf-8')
    (root / 'agent.md').write_text('Custom agent in {{workdir}}.\nRead working-request.json.\n', encoding='utf-8')
    (root / 'instructions.md').write_text('Only libraries needed.\n\nOnly terminal helper.\n', encoding='utf-8')
    monkeypatch.setattr(system_prompt, '_ROOT', root)
    return root


def test_packaged_working_aliases_are_complete():
    aliases = json.loads((system_prompt._ROOT / 'aliases.json').read_text(encoding='utf-8'))
    assert set(aliases) == {'working.agent', 'working.instructions', 'working.etc', 'working.benchmark',
                            'planner.training_research', 'planner.etc', 'planner.benchmark', 'search.node',
                            'search.node_instructions', 'search.query', 'search.stage_goals'}
    for alias in ('search.node', 'search.query'):
        assert 'fixture' in system_prompt.load_prompt(alias, workdir='fixture')
    assert set(json.loads(system_prompt.load_prompt('search.stage_goals'))) == {'1','2','3','4'}
    assert 'one search node' in system_prompt.load_prompt('search.node_instructions')
    agent = system_prompt.load_prompt('working.agent', workdir='fixture')
    instructions = system_prompt.load_prompt('working.instructions').split('\n\n')
    assert 'Request workspace: fixture\nRead working-request.json, then perform the approved work through terminal.py.' in agent
    assert any('never create debug child nodes' in item for item in instructions)
    assert any('Only the user creates improve runs' in item for item in instructions)
    assert any('approved.snapshot.resources[*].file_path' in instruction for instruction in instructions)
    assert any('do not print full package inventories' in item for item in instructions)


def test_reload_contents_and_alias_without_restart(prompt_root):
    assert system_prompt.load_prompt('working.instructions') == 'Only libraries needed.\n\nOnly terminal helper.'
    (prompt_root / 'instructions.md').write_text('Updated instructions.', encoding='utf-8')
    assert system_prompt.load_prompt('working.instructions') == 'Updated instructions.'
    aliases = json.loads((prompt_root / 'aliases.json').read_text())
    aliases['working.instructions'] = 'alternate.md'
    (prompt_root / 'alternate.md').write_text('Alternate instructions.', encoding='utf-8')
    (prompt_root / 'aliases.json').write_text(json.dumps(aliases), encoding='utf-8')
    assert system_prompt.load_prompt('working.instructions') == 'Alternate instructions.'


def test_substitution_does_not_reinterpret_inserted_context(prompt_root):
    text = 'JSON {"value": "$HOME", "text": "{{keep_literal}}"}'
    assert system_prompt.load_prompt('working.agent', workdir=text) == (
        'Custom agent in ' + text + '.\nRead working-request.json.')


def test_windows_bom_and_newlines(prompt_root):
    (prompt_root / 'instructions.md').write_bytes(b'\xef\xbb\xbfFirst\r\nSecond\r\n')
    assert system_prompt.load_prompt('working.instructions') == 'First\nSecond'


def test_missing_variable_is_explicit(prompt_root):
    with pytest.raises(ValueError, match='Missing variable workdir'):
        system_prompt.load_prompt('working.agent')


def test_unknown_alias_is_explicit(prompt_root):
    with pytest.raises(ValueError, match='Unknown system prompt alias'):
        system_prompt.load_prompt('unknown')


@pytest.mark.parametrize('filename', ['../outside.md', ''])
def test_invalid_alias_target(prompt_root, filename):
    (prompt_root / 'aliases.json').write_text(json.dumps({'working.instructions': filename}), encoding='utf-8')
    with pytest.raises(ValueError):
        system_prompt.load_prompt('working.instructions')


@pytest.mark.parametrize('content', ['[]', '{broken'])
def test_invalid_alias_registry(prompt_root, content):
    (prompt_root / 'aliases.json').write_text(content, encoding='utf-8')
    with pytest.raises(ValueError):
        system_prompt.load_prompt('working.instructions')


@pytest.mark.parametrize('missing', [False, True])
def test_missing_or_empty_file(prompt_root, missing):
    path = prompt_root / 'instructions.md'
    if missing:
        path.unlink()
    else:
        path.write_text(' \n', encoding='utf-8')
    with pytest.raises((ValueError, FileNotFoundError)):
        system_prompt.load_prompt('working.instructions')


def test_working_request_uses_configured_prompt_aliases(tmp_path, prompt_root):
    async def check():
        store, project, run, worker, _, service, _, _, _ = working_fixture(tmp_path)
        try:
            workdir = service.view.root(project, run) / 'working-agent'
            workdir.mkdir(parents=True)
            request = service._request((project, run), store.approved_snapshot(project, run),
                {'remote_directory': '/fixture', 'ttl_seconds': 600}, workdir)
            saved = json.loads((workdir / 'working-request.json').read_text(encoding='utf-8'))
            assert request.prompt == f'Custom agent in {workdir}.\nRead working-request.json.'
            assert saved['instructions'][:2] == ['Only libraries needed.', 'Only terminal helper.']
            assert any('đúng một run' in item for item in saved['instructions'][2:])
            assert 'approved' in saved and saved['remote_directory'] == '/fixture'
        finally:
            await worker.close(1)
    asyncio.run(check())


@pytest.mark.parametrize('alias', ['working.agent', 'working.instructions'])
def test_invalid_prompt_fails_before_kaggle_or_reservation(tmp_path, prompt_root, alias):
    aliases = json.loads((prompt_root / 'aliases.json').read_text())
    (prompt_root / aliases[alias]).write_text('', encoding='utf-8')
    async def check():
        store, project, run, worker, _, service, _, mcp, donor = working_fixture(tmp_path)
        try:
            with pytest.raises(ValueError, match='System prompt is empty'):
                await service.start(project, run)
            assert mcp.calls == donor.opens == []
            assert service.tasks == {} and service.record(project, run) is None
            assert store.run(project, run)['state'] == 'APPROVED'
        finally:
            await worker.close(1)
    asyncio.run(check())
