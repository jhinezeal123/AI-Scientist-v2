import asyncio
import json

import pytest

from ai_scientist.workbench import system_prompt
from test_working import fixture as working_fixture


@pytest.fixture
def prompt_root(tmp_path, monkeypatch):
    root = tmp_path / 'prompts'
    root.mkdir()
    aliases = {'working.agent': 'agent.md', 'working.instructions': 'instructions.md',
               'working.task': 'task.md'}
    (root / 'aliases.json').write_text(json.dumps(aliases), encoding='utf-8')
    (root / 'agent.md').write_text('Custom agent in {{workdir}}.\n{{task_prompt}}\n', encoding='utf-8')
    (root / 'instructions.md').write_text('Only libraries needed.\n\nOnly terminal helper.\n', encoding='utf-8')
    (root / 'task.md').write_text('Read working-request.json.\n', encoding='utf-8')
    monkeypatch.setattr(system_prompt, '_ROOT', root)
    return root


def test_packaged_working_aliases_are_complete():
    task = system_prompt.load_prompt('working.task')
    agent = system_prompt.load_prompt('working.agent', workdir='fixture', task_prompt=task)
    instructions = system_prompt.load_prompt('working.instructions').split('\n\n')
    assert 'Request workspace: fixture\n' + task in agent
    assert len(instructions) == 11
    assert any('do not print full package inventories' in item for item in instructions)


def test_reload_contents_and_alias_without_restart(prompt_root):
    assert system_prompt.load_prompt('working.task') == 'Read working-request.json.'
    (prompt_root / 'task.md').write_text('Updated task.', encoding='utf-8')
    assert system_prompt.load_prompt('working.task') == 'Updated task.'
    aliases = json.loads((prompt_root / 'aliases.json').read_text())
    aliases['working.task'] = 'alternate.md'
    (prompt_root / 'alternate.md').write_text('Alternate task.', encoding='utf-8')
    (prompt_root / 'aliases.json').write_text(json.dumps(aliases), encoding='utf-8')
    assert system_prompt.load_prompt('working.task') == 'Alternate task.'


def test_substitution_does_not_reinterpret_inserted_context(prompt_root):
    text = 'JSON {"value": "$HOME", "text": "{{keep_literal}}"}'
    assert system_prompt.load_prompt('working.agent', workdir='C:\\Working', task_prompt=text) == (
        'Custom agent in C:\\Working.\n' + text)


def test_windows_bom_and_newlines(prompt_root):
    (prompt_root / 'task.md').write_bytes(b'\xef\xbb\xbfFirst\r\nSecond\r\n')
    assert system_prompt.load_prompt('working.task') == 'First\nSecond'


def test_missing_variable_is_explicit(prompt_root):
    with pytest.raises(ValueError, match='Missing variable task_prompt'):
        system_prompt.load_prompt('working.agent', workdir='fixture')


def test_unknown_alias_is_explicit(prompt_root):
    with pytest.raises(ValueError, match='Unknown system prompt alias'):
        system_prompt.load_prompt('unknown')


@pytest.mark.parametrize('filename', ['../outside.md', ''])
def test_invalid_alias_target(prompt_root, filename):
    (prompt_root / 'aliases.json').write_text(json.dumps({'working.task': filename}), encoding='utf-8')
    with pytest.raises(ValueError):
        system_prompt.load_prompt('working.task')


@pytest.mark.parametrize('content', ['[]', '{broken'])
def test_invalid_alias_registry(prompt_root, content):
    (prompt_root / 'aliases.json').write_text(content, encoding='utf-8')
    with pytest.raises(ValueError):
        system_prompt.load_prompt('working.task')


@pytest.mark.parametrize('missing', [False, True])
def test_missing_or_empty_file(prompt_root, missing):
    path = prompt_root / 'task.md'
    if missing:
        path.unlink()
    else:
        path.write_text(' \n', encoding='utf-8')
    with pytest.raises((ValueError, FileNotFoundError)):
        system_prompt.load_prompt('working.task')


def test_working_request_uses_configured_prompt_aliases(tmp_path, prompt_root):
    async def check():
        store, project, run, worker, _, service, _, _, _ = working_fixture(tmp_path)
        try:
            workdir = service.view.root(project, run) / 'working-agent'
            workdir.mkdir(parents=True)
            request = service._request((project, run), store.approved_snapshot(project, run),
                {'remote_directory': '/fixture', 'ttl_seconds': 600}, workdir)
            saved = json.loads((workdir / 'working-request.json').read_text())
            assert request.prompt == 'Read working-request.json.'
            assert saved['instructions'] == ['Only libraries needed.', 'Only terminal helper.']
            assert 'approved' in saved and saved['remote_directory'] == '/fixture'
        finally:
            await worker.close(1)
    asyncio.run(check())


@pytest.mark.parametrize('alias', ['working.agent', 'working.instructions', 'working.task'])
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
