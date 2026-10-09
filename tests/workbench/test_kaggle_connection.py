"""Environment regression for the backend-owned MCP subprocess."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from ai_scientist.workbench import kaggle


@pytest.mark.parametrize('platform,programdata,port,expected', [
    ('win32', r'C:\ProgramData', None, {'PROGRAMDATA': r'C:\ProgramData'}),
    ('win32', None, None, {}),
    ('linux', r'C:\ProgramData', None, {}),
    ('win32', r'C:\ProgramData', '8023', {'PROGRAMDATA': r'C:\ProgramData',
        'AI_SCIENTIST_KAGGLE_PROXY_PORT': '8023'}),
])
def test_mcp_inherits_only_required_environment(monkeypatch, tmp_path, platform, programdata, port, expected):
    captured = []
    monkeypatch.setattr(kaggle, 'sys', SimpleNamespace(platform=platform))
    if port is None:
        monkeypatch.delenv('AI_SCIENTIST_KAGGLE_PROXY_PORT', raising=False)
    else:
        monkeypatch.setenv('AI_SCIENTIST_KAGGLE_PROXY_PORT', port)
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
