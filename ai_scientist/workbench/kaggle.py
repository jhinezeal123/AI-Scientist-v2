"""One stdio MCP session for the app lifetime; no SDK or account credentials."""
from contextlib import asynccontextmanager
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def connect_mcp(config):
    params = StdioServerParameters(command=str(config.donor_python),
                                  args=[str(config.donor_root / "mcp_server.py")],
                                  cwd=str(config.donor_root))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            async with asyncio.timeout(20):
                await session.initialize()
                tools = await session.list_tools()
            yield session, [tool.name for tool in tools.tools]
