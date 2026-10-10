"""Agent-management boundary: existing Workbench talks to one AgentGateway alias.

Implementation is intentionally isolated in the root-level "agent management" folder.
Only ai_scientist.workbench.runtime imports this package via a pinned local path.
"""
from .gateway import AgentGateway
from .spec import GatewaySpec, load_spec
from .store import AgentStore

__all__ = ["AgentGateway", "GatewaySpec", "load_spec", "AgentStore"]
