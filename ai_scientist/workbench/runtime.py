"""Construct the product-owned Codex runtime at the bootstrap boundary."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeBindings:
    runtime: object
    request_type: type
    uncertain_error: type[BaseException] | None = None


def load_runtime(config):
    from .agents import contracts, codex
    runtime = codex.CodexCliRuntime(str(config.codex_executable), config.codex_model,
                                   config.codex_reasoning_effort)
    return RuntimeBindings(runtime, contracts.RuntimeRequest, contracts.RuntimeUncertain)
