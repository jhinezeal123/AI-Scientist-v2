"""Construct the single agent alias at the Workbench bootstrap boundary."""
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys


@dataclass(frozen=True)
class RuntimeBindings:
    runtime: object
    request_type: type
    uncertain_error: type[BaseException] | None = None


def _agent_gateway_class():
    """Load a root-level module from the literally named 'agent management' folder.

    No sys.path mutation, editable install, second Python service or duplicate
    agent implementation inside ai_scientist/workbench.
    """
    module_name = "_ai_scientist_agent_management"
    if module_name not in sys.modules:
        root = Path(__file__).resolve().parents[2]
        package = root / "agent management" / "agent_management"
        spec = importlib.util.spec_from_file_location(
            module_name, package / "__init__.py",
            submodule_search_locations=[str(package)])
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to load agent management module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
    return sys.modules[module_name].AgentGateway


def load_runtime(config):
    from .agents import contracts, codex
    # Preserve the installed Codex adapter and its exact settings as the default.
    legacy_runtime = codex.CodexCliRuntime(
        str(config.codex_executable), config.codex_model, config.codex_reasoning_effort)
    agent_alias = _agent_gateway_class()(legacy_runtime, config.workspace_root)
    return RuntimeBindings(agent_alias, contracts.RuntimeRequest, contracts.RuntimeUncertain)
