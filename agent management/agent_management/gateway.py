"""Single alias consumed by Workbench; all provider and coordination logic stays here."""
from __future__ import annotations

from pathlib import Path
import shutil
from threading import RLock
from typing import Any

from .acp import AcpStdioRuntime
from .spec import GatewaySpec, load_spec
from .store import AgentStore


class AgentGateway:
    """Compatible with existing synchronous AgentRuntime.run(request, progress, cancelled).

    Legacy Workbench still invokes exactly one runtime alias, without delegation,
    retries, prompt rewriting or new research admission paths. A configured
    alternate seat/provider is explicit and never silently falls back to Codex.
    Multi-agent coordination is an opt-in management surface, *not* permission
    to run experiments.
    """

    def __init__(self, codex_runtime: Any, workspace_root: Path, *,
                 spec_path: Path | None = None):
        self.codex_runtime = codex_runtime
        self.workspace_root = Path(workspace_root)
        self.spec_path = spec_path or (
            self.workspace_root / ".workbench" / "agent-management.json")
        self.spec: GatewaySpec = load_spec(self.spec_path)
        self._store: AgentStore | None = None
        self._platform = None
        self._lock = RLock()
        self.protected_paths = ()

    @property
    def store(self) -> AgentStore:
        with self._lock:
            if self._store is None:
                self._store = AgentStore(
                    self.workspace_root / ".workbench" / "agent-management.sqlite")
        return self._store

    @property
    def platform(self):
        with self._lock:
            if self._platform is None:
                from .orchestrator import TeamPlatform
                self._platform = TeamPlatform(self.store, self.workspace_root, codex=self.codex_runtime, protected=self.protected_paths)
            return self._platform

    def close(self):
        if self._platform is not None:
            return self._platform.close()

    def run(self, request, progress, cancelled):
        profile = self.spec.for_role(request.role)
        if profile.kind == "native_codex":
            # Golden path: same request object, callbacks, Codex process and result.
            if self._platform is not None and __import__('os').name=='nt':
                from .windows_isolation import lease, refresh_scope, protect_scope
                path=Path(str(request.workdir).removeprefix('\\\\?\\'))
                owned=path.resolve().is_relative_to((self.workspace_root/'.workbench/projects').resolve())
                with lease(request.timeout_seconds,cancelled):
                    if owned:
                        refresh_scope(self.workspace_root,[path],legacy=True)
                    try:
                        return self.codex_runtime.run(request,progress,cancelled)
                    finally:
                        if owned:
                            protect_scope(self.workspace_root,[path],legacy=True)
            return self.codex_runtime.run(request, progress, cancelled)
        if profile.kind == "acp":
            return AcpStdioRuntime(
                profile.executable, profile.args, model=profile.model,
            ).run(request, progress, cancelled)
        raise ValueError("Unknown runtime provider; no implicit fallback")

    def capabilities(self) -> list[dict]:
        """Read-only readiness probe; never authenticates, starts or installs agents."""
        result = []
        for name, provider in self.spec.providers.items():
            if provider.kind == "native_codex":
                ready = True  # Configured by the existing Workbench loader.
                features = ["one_shot", "structured_result", "cancel"]
            else:
                ready = bool(shutil.which(provider.executable) or
                             (Path(provider.executable).is_file()))
                features = ["one_shot", "acp_v1", "cancel"]
            result.append({"name": name, "kind": provider.kind, "ready": ready,
                           "features": features})
        return result

    def create_rig(self, rig_id: str, *, seats: list[str]) -> dict:
        if not seats or len(seats) != len(set(seats)):
            raise ValueError("Rig requires distinct seats")
        if any(seat not in self.spec.seats for seat in seats):
            raise ValueError("Rig references an unconfigured seat")
        return self.store.create_rig(rig_id, {
            "version": 1, "seats": [
                {"id": name, "provider": self.spec.seats[name].provider}
                for name in seats
            ]
        })

    def enqueue(self, rig_id: str, seat: str, request_id: str,
                task: dict, *, depends_on: str | None = None) -> dict:
        if seat not in self.spec.seats:
            raise ValueError("Unconfigured seat")
        # Only records work metadata; no run/submit side effect or auto-execution.
        return self.store.enqueue(rig_id, seat, request_id, task,
                                  depends_on=depends_on)

    def claim(self, rig_id: str, seat: str, *, lease_seconds: int = 300):
        if seat not in self.spec.seats:
            raise ValueError("Unconfigured seat")
        return self.store.claim(rig_id, seat, lease_seconds=lease_seconds)

    def finish(self, task_id: str, lease_token: str, *, result: dict | None = None,
               uncertain: bool = False):
        return self.store.finish(task_id, lease_token, result=result, uncertain=uncertain)

    def send(self, rig_id: str, sender: str, recipient: str, body: str) -> int:
        if sender not in self.spec.seats or (recipient != "*" and recipient not in self.spec.seats):
            raise ValueError("Message actor is not a configured seat")
        return self.store.send(rig_id, sender, recipient, body)

    def inbox(self, rig_id: str, seat: str, *, after: int = 0) -> list[dict]:
        if seat not in self.spec.seats:
            raise ValueError("Unknown seat")
        return self.store.inbox(rig_id, seat, after=after)

    def snapshot(self, rig_id: str) -> dict:
        return self.store.snapshot(rig_id)
