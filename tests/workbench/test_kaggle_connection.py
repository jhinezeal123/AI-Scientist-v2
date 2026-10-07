"""Environment regression for the backend-owned MCP subprocess."""
import asyncio
from contextlib import asynccontextmanager, nullcontext
from types import SimpleNamespace

import pytest

from ai_scientist.workbench import kaggle


@pytest.mark.parametrize('platform,programdata,expected', [
    ('win32', r'C:\ProgramData', {'PROGRAMDATA': r'C:\ProgramData'}),
    ('win32', None, {}),
    ('linux', r'C:\ProgramData', {}),
])
def test_mcp_inherits_only_required_windows_environment(monkeypatch, tmp_path, platform, programdata, expected):
    captured = []
    monkeypatch.setattr(kaggle, 'sys', SimpleNamespace(platform=platform))
    monkeypatch.setattr(kaggle.socket, 'create_connection', lambda *a, **k: nullcontext())
    monkeypatch.setenv('KAGGLE_API_TOKEN', 'must-not-be-inherited')
    if programdata is None:
        monkeypatch.delenv('PROGRAMDATA', raising=False)
    else:
        monkeypatch.setenv('PROGRAMDATA', programdata)

    @asynccontextmanager
    async def stdio(params):
        captured.append(params)
        yield 'reader', 'writer'

    class Session:
        def __init__(self, reader, writer):
            assert (reader, writer) == ('reader', 'writer')

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def initialize(self):
            pass

        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name='kaggle_ssh_start')])

    monkeypatch.setattr(kaggle, 'stdio_client', stdio)
    monkeypatch.setattr(kaggle, 'ClientSession', Session)
    config = SimpleNamespace(donor_python=tmp_path / 'python.exe', donor_root=tmp_path)

    async def connect():
        async with kaggle.connect_mcp(config) as (_, names):
            assert names == ['kaggle_ssh_start']

    asyncio.run(connect())
    assert len(captured) == 1
    assert captured[0].env == expected
    assert captured[0].cwd == str(tmp_path)
    assert captured[0].args == [str(tmp_path / 'mcp_server.py')]
