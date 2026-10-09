"""Native Kaggle CLI boundary: explicit account, JSON input and OS environment."""
import json
from types import SimpleNamespace

import pytest

from ai_scientist.workbench import ssh_terminal


@pytest.mark.parametrize('action', ['start', 'idle'])
@pytest.mark.parametrize('port', [None, '8023'])
def test_native_cli_account_and_environment(monkeypatch, tmp_path, action, port):
    captured = []
    monkeypatch.setenv('PROGRAMDATA', r'C:\ProgramData')
    monkeypatch.setenv('KAGGLE_API_TOKEN', 'must-not-be-inherited')
    monkeypatch.setenv('OPENAI_API_KEY', 'must-not-be-inherited')
    if port is None:
        monkeypatch.delenv('AI_SCIENTIST_KAGGLE_PROXY_PORT', raising=False)
    else:
        monkeypatch.setenv('AI_SCIENTIST_KAGGLE_PROXY_PORT', port)

    class Process:
        returncode = 0
        stdin = stdout = stderr = None

        def __init__(self, command, **options):
            captured.append({'command': command, **options})

        def communicate(self, data, timeout):
            captured[-1].update(data=data, timeout=timeout)
            return b'{"verified":true}', b''

        def poll(self):
            return self.returncode

    monkeypatch.setattr(ssh_terminal.subprocess, 'Popen', Process)
    config = SimpleNamespace(donor_python=tmp_path/'python.exe', donor_root=tmp_path/'kaggle mcp',
                             kaggle_account_alias='selected-account')
    donor = ssh_terminal.DonorSession(config)
    arguments = {'account': config.kaggle_account_alias, 'request_id': 'a'*32}
    result = donor.start(arguments) if action == 'start' else donor.account_idle()
    assert result == {'verified': True} and len(captured) == 1
    call = captured[0]
    assert call['command'] == [str(config.donor_python), '-m', 'interface_ai_scientist', action,
                               '--account', 'selected-account']
    assert call['cwd'] == config.donor_root
    assert call['env']['PROGRAMDATA'] == r'C:\ProgramData'
    assert call['env'].get('AI_SCIENTIST_KAGGLE_PROXY_PORT') == port
    assert 'KAGGLE_API_TOKEN' not in call['env'] and 'OPENAI_API_KEY' not in call['env']
    assert call['env']['PYTHONUTF8'] == '1'
    assert (json.loads(call['data']) if action == 'start' else call['data']) == (arguments if action == 'start' else None)
    assert call['timeout'] == (270 if action == 'start' else 60)
