import base64
import hashlib
import io
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_scientist.workbench.ssh_terminal import AgentTerminalBridge, SshTerminal, TerminalDisconnected, collect_files
from ai_scientist.workbench.agents.codex import CodexCliRuntime
from ai_scientist.workbench.codex_executable import resolve_codex_executable


PROTOCOL = '''import json,sys
print(json.dumps({'type':'ready','protocol':1}),flush=True)
count=0
for line in sys.stdin:
    req=json.loads(line)
    count+=1
    if req['action']=='exec':
        print(json.dumps({'type':'output','id':req['id'],'text':'fixture '+str(count)+'\\n'}),flush=True)
    print(json.dumps({'type':'result','id':req['id'],'returncode':0,'command_count':count}),flush=True)
'''


def test_one_process_terminal_serializes_commands_and_does_not_replay(tmp_path):
    output = []
    process = subprocess.Popen([sys.executable, '-u', '-c', PROTOCOL],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    terminal = SshTerminal(process, output.append)
    try:
        first = terminal.request('exec', command='first', timeout=1)
        second = terminal.request('exec', command='second', timeout=1)
        assert first['command_count'] == 1 and second['command_count'] == 2
        assert ''.join(output) == 'fixture 1\nfixture 2\n'
        assert terminal.process is process
    finally:
        terminal.close()
    with pytest.raises(TerminalDisconnected):
        terminal.request('exec', command='do not replay', timeout=1)
    assert process.poll() is not None


def test_failed_handshake_closes_child():
    process = subprocess.Popen([sys.executable, '-c', 'pass'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with pytest.raises(TerminalDisconnected):
        SshTerminal(process, lambda text: None)
    assert process.poll() is not None


def test_bridge_restricts_backend_actions_and_invalid_arguments(tmp_path):
    class Terminal:
        def request(self, action, **body):
            return {'output': 'fixture', 'returncode': 0}
    bridge = AgentTerminalBridge(Terminal(), tmp_path)
    access = json.loads(bridge.access.read_text())
    def call(body, token):
        request = urllib.request.Request(access['url'], json.dumps(body).encode(),
            {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.load(response)
    try:
        assert call({'action': 'exec', 'command': 'fixture'}, access['token'])['returncode'] == 0
        for body, token, code in [({'action': 'stop'}, access['token'], 400),
            ({'action': 'exec', 'command': 'fixture', 'id': 'override'}, access['token'], 400),
            ({'action': 'exec', 'command': 'fixture'}, 'wrong', 403)]:
            with pytest.raises(urllib.error.HTTPError) as error:
                call(body, token)
            assert error.value.code == code
    finally:
        bridge.close()
    assert not bridge.access.exists()


@pytest.mark.parametrize('name', ['../escape', 'C:/outside', 'source/../../outside', 'output\\escape', 'working-agent/terminal-access.json'])
def test_artifact_paths_are_restricted(tmp_path, name):
    class Terminal:
        def request(self, action, **body):
            return {'files': [{'path': name, 'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()}]}
    with pytest.raises(ValueError):
        collect_files(Terminal(), tmp_path, 100)


def test_artifact_bytes_and_hash_are_checked(tmp_path):
    class Terminal:
        def request(self, action, **body):
            if action == 'manifest':
                return {'files': [{'path': 'output/test.csv', 'bytes': 5, 'sha256': '0' * 64}]}
            return {'data': base64.b64encode(b'wrong').decode()}
    with pytest.raises(ValueError, match='hash mismatch'):
        collect_files(Terminal(), tmp_path, 100)
    assert not (tmp_path / 'output/test.csv').exists()


def test_codex_path_recovery_and_working_cli_options(tmp_path, monkeypatch):
    executable = tmp_path / 'current.exe'
    executable.write_bytes(b'fixture executable; not launched')
    monkeypatch.setattr('ai_scientist.workbench.codex_executable.shutil.which', lambda name: str(executable))
    assert resolve_codex_executable(tmp_path / 'removed.exe') == executable
    payload = {'succeeded': True, 'summary': 'fixture', 'limitations': [], 'output_files': []}
    events = [
        {'type': 'thread.started', 'thread_id': 'fixture'},
        {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps({'text': json.dumps(payload), 'files': {}})}},
        {'type': 'turn.completed'}]
    arguments = []
    class Process:
        returncode = 0
        def __init__(self):
            self.stdout = io.BytesIO(('\n'.join(json.dumps(event) for event in events)).encode())
            self.stderr = io.BytesIO()
        def poll(self):
            return 0
    def launch(args, **options):
        arguments.extend(args)
        return Process()
    monkeypatch.setattr('ai_scientist.workbench.agents.codex.subprocess.Popen', launch)
    runtime = CodexCliRuntime(str(tmp_path / 'removed.exe'), model='fixture', reasoning_effort='max')
    request = SimpleNamespace(role='mvp0_working', workdir=tmp_path, prompt='fixture', timeout_seconds=1, max_output_bytes=100000)
    result = runtime.run(request, lambda event: None, lambda: False)
    assert json.loads(result.text) == payload
    assert arguments[0] == str(executable) and '--ignore-user-config' in arguments
    assert arguments[arguments.index('--sandbox') + 1] == 'workspace-write'
    assert 'sandbox_workspace_write.network_access=true' in arguments
