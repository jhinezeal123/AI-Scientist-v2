"""Thin CLI/TUI/MCP client; does not start a second scheduler or server."""
import importlib
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ai_scientist.workbench.runtime import _agent_gateway_class

if __name__=='__main__':
    package=_agent_gateway_class().__module__.rsplit('.',1)[0]
    importlib.import_module(package+'.interfaces').main()
