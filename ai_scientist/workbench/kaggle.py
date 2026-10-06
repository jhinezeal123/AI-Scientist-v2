"""One stdio MCP session for the app lifetime; no SDK or account credentials."""
from contextlib import asynccontextmanager
import asyncio
import socket
import subprocess

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def connect_mcp(config):
    def proxy_listening():
        try:
            with socket.create_connection(('127.0.0.1',80),timeout=0.5):
                return True
        except OSError:
            return False
    proxy = None
    if not await asyncio.to_thread(proxy_listening):
        # Legacy donor push uses its localhost proxy. Explicit selected token is preserved.
        log_dir = config.workspace_root/'.workbench/logs'
        log_dir.mkdir(parents=True,exist_ok=True)
        with (log_dir/'kaggle-proxy.log').open('ab') as log:
            proxy = await asyncio.create_subprocess_exec(str(config.donor_python),str(config.donor_root/'proxy.py'),
                        cwd=str(config.donor_root),stdout=log,stderr=asyncio.subprocess.STDOUT,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for _ in range(30):
            if await asyncio.to_thread(proxy_listening):
                break
            if proxy.returncode is not None:
                raise RuntimeError('Donor proxy failed to start on port80')
            await asyncio.sleep(0.1)
        else:
            proxy.terminate()
            await proxy.wait()
            raise RuntimeError('Donor proxy did not become ready on port80')
    params = StdioServerParameters(command=str(config.donor_python),
                                  args=[str(config.donor_root / "mcp_server.py")],
                                  cwd=str(config.donor_root))
    try:
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                async with asyncio.timeout(20):
                    await session.initialize()
                    tools = await session.list_tools()
                yield session, [tool.name for tool in tools.tools]
    finally:
        if proxy and proxy.returncode is None:
            proxy.terminate()
            await proxy.wait()
