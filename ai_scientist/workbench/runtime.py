"""Load the original donor runtime only at the configured bootstrap boundary."""
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeBindings:
    runtime: object
    request_type: type
    uncertain_error: type[BaseException] | None = None


def load_runtime(config):
    donor = config.donor_root.resolve()
    for name, module in tuple(sys.modules.items()):
        if name == "agent_platform" or name.startswith("agent_platform."):
            origin = getattr(module, "__file__", None)
            if origin and not Path(origin).resolve().is_relative_to(donor):
                raise ValueError("A different donor agent_platform is already loaded")
    if str(donor) not in sys.path:
        sys.path.insert(0, str(donor))
    ports = importlib.import_module("agent_platform.ports.agent_runtime")
    adapter = importlib.import_module("agent_platform.infrastructure.agent_runtime")
    importlib.import_module("agent_platform.ports.research_outputs")
    runtime = adapter.CodexCliRuntime(str(config.codex_executable), config.codex_model,
                                     config.codex_reasoning_effort)
    return RuntimeBindings(runtime, ports.RuntimeRequest, ports.RuntimeUncertain)
