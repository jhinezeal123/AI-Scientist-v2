"""Backend restart restores local authentication without replacing explicit secrets."""
import os

import pytest

from ai_scientist.workbench.__main__ import restore_control_token


@pytest.mark.parametrize('explicit', ['', 'explicit-fixture-token'])
def test_saved_control_token_after_restart(tmp_path, monkeypatch, explicit):
    monkeypatch.setenv('AI_SCIENTIST_AGENT_CONTROL_TOKEN', explicit)
    folder = tmp_path / '.workbench'
    folder.mkdir()
    (folder / 'agent-control-token.txt').write_text(' saved-fixture-token\n', encoding='utf-8')
    restore_control_token(tmp_path)
    assert os.environ['AI_SCIENTIST_AGENT_CONTROL_TOKEN'] == (explicit or 'saved-fixture-token')


def test_missing_local_token_keeps_management_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv('AI_SCIENTIST_AGENT_CONTROL_TOKEN', raising=False)
    restore_control_token(tmp_path)
    assert not os.environ.get('AI_SCIENTIST_AGENT_CONTROL_TOKEN')
