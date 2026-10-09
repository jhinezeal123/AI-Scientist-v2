"""Minimal backend interface: SSH bootstrap and account-wide idle verification."""
from mcp.server.fastmcp import FastMCP
from interface_ai_scientist.mcp_tools import register
from account_runtime import account_idle
from proxy_control import ensure_proxy

mcp = FastMCP('ai-scientist-kaggle')
register(mcp)


@mcp.tool()
def workbench_account_idle(account: str) -> dict:
    """Verify cookie identity and all active sessions; fail closed if unverified."""
    return account_idle(account)


if __name__ == '__main__':
    proxy = ensure_proxy()
    try:
        mcp.run()
    finally:
        if proxy and proxy.poll() is None:
            proxy.terminate()
            proxy.wait(timeout=5)
