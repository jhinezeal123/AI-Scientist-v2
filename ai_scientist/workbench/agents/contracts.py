"""Narrow boundary to an explicitly authorized local or remote agent runtime."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol


class RuntimeCancelled(RuntimeError):
    """The exact local agent attempt was stopped by its cancellation signal."""


class RuntimePermissionRequired(RuntimeError):
    """An agent requested a tool capability requiring a human decision."""


class RuntimeUncertain(RuntimeError):
    """An agent attempt stopped being observable: its process could not be confirmed dead.

    Killing a local child is best effort, so a caller must treat this as an unknown outcome: no
    cancellation is acknowledged, no result is reported for the attempt and it is never replayed.
    """


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    request_id: str
    role: str
    prompt: str
    workdir: Path
    timeout_seconds: int = 300
    max_output_bytes: int = 3_000_000


@dataclass(frozen=True, slots=True)
class RuntimeProgress:
    stage: str
    message: str
    permission_required: bool = False


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    text: str
    files: dict[str, bytes] = field(default_factory=dict)
    session_id: str | None = None
    usage: dict[str, int | float] = field(default_factory=dict)


class AgentRuntime(Protocol):
    def run(self, request: RuntimeRequest, progress: Callable[[RuntimeProgress], None],
            cancelled: Callable[[], bool]) -> RuntimeResult: ...
