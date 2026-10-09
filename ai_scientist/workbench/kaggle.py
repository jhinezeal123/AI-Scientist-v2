"""One stdio MCP session for the app lifetime; no SDK or account credentials."""
from contextlib import asynccontextmanager
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def connect_mcp(config):
    # The MCP owns its proxy lifecycle and verifies its identity. The backend
    # must not borrow or start a separate legacy service on port 80.
    # MCP's default Windows environment omits PROGRAMDATA. Win32 OpenSSH needs
    # it even for `ssh -V`; without it the donor's SSH exits 255 silently.
    donor_env = {}
    if sys.platform == 'win32' and os.environ.get('PROGRAMDATA'):
        donor_env['PROGRAMDATA'] = os.environ['PROGRAMDATA']
    if os.environ.get('AI_SCIENTIST_KAGGLE_PROXY_PORT'):
        donor_env['AI_SCIENTIST_KAGGLE_PROXY_PORT'] = os.environ['AI_SCIENTIST_KAGGLE_PROXY_PORT']
    params = StdioServerParameters(command=str(config.donor_python),
                                  args=[str(config.donor_root / "mcp_server.py")],
                                  cwd=str(config.donor_root), env=donor_env)
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            async with asyncio.timeout(20):
                await session.initialize()
                tools = await session.list_tools()
            yield session, [tool.name for tool in tools.tools]


def decode_result(result):
    if getattr(result, 'isError', False):
        # MCP errors may include provider details; keep credentials/raw errors out of app evidence.
        raise RuntimeError('MCP operation failed; outcome must be reconciled')
    structured = getattr(result, 'structuredContent', None)
    if isinstance(structured, dict):
        # FastMCP wraps primitive string returns; legacy tools return JSON strings.
        if set(structured) == {'result'} and isinstance(structured['result'], str):
            structured = json.loads(structured['result'])
        if isinstance(structured, dict):
            return structured
    content = getattr(result, 'content', [])
    texts = [item.text for item in content if getattr(item, 'type', None) == 'text']
    if len(texts) != 1:
        raise ValueError('Expected one structured MCP response')
    value = json.loads(texts[0])
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError('Expected MCP object response')
    return value
