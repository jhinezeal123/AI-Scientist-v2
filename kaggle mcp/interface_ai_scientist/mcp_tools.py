"""Existing MCP boundary delegates to the reusable bootstrap core."""
from .bootstrap_service import start


def register(mcp):
    mcp.tool(name="kaggle_ssh_start")(start)
