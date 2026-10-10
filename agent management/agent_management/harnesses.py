"""Session contract and native harnesses. Harness identity is separate from model."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
import subprocess
import threading
from typing import Callable, Protocol
import uuid

from .models import AgentSpec, HarnessSpec, TaskResult
from .processes import run_process

RESULT_SCHEMA = {"type": "object", "additionalProperties": False,
    "required": ["summary", "files", "checks", "handoff"], "properties": {
        "summary": {"type": "string"}, "handoff": {"type": "string"},
        "checks": {"type": "array", "items": {"type": "string"}},
        "files": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "required": ["path", "content"], "properties": {"path": {"type": "string"}, "content": {"type": "string"}}}}}}


@dataclass(frozen=True)
class Capabilities:
    stream: bool = True
    models: bool = True
    plan: bool = False
    tool_approval: bool = False
    resume: bool = False
    fork: bool = False
    list_sessions: bool = False
    file_edits: bool = True  # Structured, validated edits applied by the workspace service.
    terminal: bool = False
    usage: bool = False


@dataclass
class SessionHandle:
    id: str
    seat: AgentSpec
    workspace: Path
    provider_session: str | None = None
    fork: bool = False
    interrupted: threading.Event = field(default_factory=threading.Event)
    stop_receipt: dict | None = None


@dataclass(frozen=True)
class TurnResult:
    result: TaskResult
    provider_session: str | None
    receipt: dict
    usage: dict = field(default_factory=dict)


class HarnessAdapter(Protocol):
    def probe(self) -> dict: ...
    def start(self, seat: AgentSpec, workspace: Path) -> SessionHandle: ...
    def send(self, handle: SessionHandle, message: str, *, request_id: str,
             timeout: int, emit: Callable, started: Callable) -> TurnResult: ...
    def approve(self, handle: SessionHandle, permission_id: str, decision: str): ...
    def interrupt(self, handle: SessionHandle): ...
    def resume(self, handle: SessionHandle, provider_session: str) -> SessionHandle: ...
    def close(self, handle: SessionHandle): ...


class NativeHarness:
    def __init__(self, spec: HarnessSpec, *, codex=None, sandbox=None):
        self.spec = spec
        self.codex = codex
        self.sandbox = sandbox
        self._fork_supported = None

    @property
    def capabilities(self):
        return Capabilities(resume=self.spec.kind in {"native_codex", "native_claude"},
                            fork=self.spec.kind == "native_claude" or self.codex_fork_supported(), usage=self.spec.kind != "cli_json")

    def codex_fork_supported(self):
        if self.spec.kind!='native_codex':
            return False
        if self._fork_supported is None:
            try:
                result=subprocess.run([self.executable(),'exec','fork','--help'],capture_output=True,timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if __import__('os').name=='nt' else 0)
                self._fork_supported=result.returncode==0 and b'Usage: codex exec fork' in result.stdout
            except (OSError,ValueError,subprocess.SubprocessError):
                self._fork_supported=False
        return self._fork_supported

    def executable(self):
        configured = self.spec.executable
        if self.spec.kind == "native_codex" and not configured:
            configured = getattr(self.codex, "executable", "")
        if self.spec.kind == "native_claude" and not configured:
            configured = shutil.which("claude.exe") or shutil.which("claude") or ""
        candidate = shutil.which(configured) or configured
        if not candidate or not Path(candidate).is_file() or Path(candidate).suffix.lower() in {".cmd", ".bat", ".ps1"}:
            raise ValueError("Harness is unavailable; configure its installed native executable")
        return str(Path(candidate).resolve())

    def probe(self):
        from dataclasses import asdict
        try:
            executable = self.executable()
            # Version/readiness probes do not initialize a model session or install a CLI.
            result = subprocess.run([executable, "--version"], capture_output=True, timeout=10,
                                    encoding="utf-8", errors="replace",
                                    creationflags=subprocess.CREATE_NO_WINDOW if __import__("os").name == "nt" else 0)
            ready = result.returncode == 0
            version = result.stdout.strip()[:200]
        except (OSError, ValueError, subprocess.SubprocessError):
            ready, version = False, None
        models = self.spec.models[:]
        if self.spec.kind == "native_codex" and not models and getattr(self.codex, "model", None):
            models = [self.codex.model]
        return {"id": self.spec.id, "kind": self.spec.kind, "ready": ready,
                "auth": "not_probed", "version": version, "models": models,
                "capabilities": asdict(self.capabilities),
                "isolation": "read-only native sandbox + validated edits" if self.spec.kind == "native_codex" else "tools disabled + validated edits"}

    def start(self, seat, workspace):
        if not self.spec.enabled:
            raise ValueError("Harness is disabled")
        self.executable()
        if self.spec.models and seat.model and seat.model not in self.spec.models:
            raise ValueError("Selected model is not in the harness catalog")
        return SessionHandle(uuid.uuid4().hex, seat, Path(workspace))

    def resume(self, handle, provider_session):
        if not self.capabilities.resume:
            raise ValueError("Harness resume is unsupported")
        uuid.UUID(provider_session)
        handle.provider_session = provider_session
        return handle

    def fork(self, handle, provider_session):
        if not self.capabilities.fork:
            raise ValueError("Harness fork is unsupported")
        self.resume(handle, provider_session)
        handle.fork = True
        return handle

    def interrupt(self, handle):
        handle.interrupted.set()

    def close(self, handle):
        self.interrupt(handle)

    def approve(self, handle, permission_id, decision):
        raise ValueError("Native tool requests are disabled; edits use the seat policy")

    def send(self, handle, message, *, request_id, timeout, emit, started):
        executable = self.executable()
        model = handle.seat.model or (getattr(self.codex, "model", None) if self.spec.kind == "native_codex" else None)
        prompt = ("Return only the requested JSON object. Do not call local tools, install software, access credentials or independently create research sessions. "
                  "You may return requested structured remote actions as JSON; the backend executes them only in an already authorized session.\n" + message)
        schema_file = handle.workspace / ".team-result-schema.json"
        if schema_file.is_symlink():
            raise ValueError("Refusing redirected result schema")
        schema_file.write_text(json.dumps(RESULT_SCHEMA), encoding="utf-8")
        try:
            if self.spec.kind == "native_codex":
                args = [executable, "exec"]
                if handle.provider_session:
                    args += ["fork" if handle.fork else "resume", handle.provider_session]
                args += ["--json", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
                         "--output-schema", str(schema_file), "--config", 'sandbox_mode="read-only"',
                         "--config", 'approval_policy="never"', "--config", 'web_search="disabled"']
                if not handle.provider_session:
                    args += ["--sandbox", "read-only", "--cd", str(handle.workspace)]
                for feature in ("shell_tool", "unified_exec", "hooks", "apps", "computer_use", "browser_use",
                                "browser_use_external", "image_generation", "workspace_dependencies", "skill_search", "view_image"):
                    args += ["--disable", feature]
                args += ["--enable", "skip_host_skill_discovery"]
                if model:
                    args += ["--model", model]
                if getattr(self.codex, "reasoning_effort", None):
                    args += ["--config", 'model_reasoning_effort="' + self.codex.reasoning_effort + '"']
                args += ["-"]
                body = prompt.encode()
            elif self.spec.kind == "native_claude":
                args = [executable, "--print", "--output-format", "stream-json", "--verbose", "--tools", "",
                        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--safe-mode", "--no-chrome",
                        "--setting-sources", "", "--permission-mode", "dontAsk", "--json-schema", json.dumps(RESULT_SCHEMA)]
                if model:
                    args += ["--model", model]
                if handle.provider_session:
                    args += ["--resume", handle.provider_session]
                    if handle.fork:
                        args += ["--fork-session"]
                body = prompt.encode()
            else:
                args = [executable, *self.spec.args]
                body = json.dumps({"request_id": request_id, "prompt": prompt, "model": model,
                                   "workdir": str(handle.workspace), "result_schema": RESULT_SCHEMA}).encode()
                if self.sandbox:
                    args = self.sandbox(handle, args)
            raw, receipt = run_process(args, handle.workspace, body, timeout=timeout,
                                       cancelled=handle.interrupted.is_set, emit=emit, started=started)
            handle.stop_receipt = receipt
        finally:
            schema_file.unlink(missing_ok=True)
        if self.spec.kind == "native_codex":
            final, provider_session, usage, completed = None, None, {}, False
            for line in raw.decode("utf-8").splitlines():
                event = json.loads(line)
                if event.get("type") == "thread.started":
                    provider_session = event.get("thread_id")
                if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message":
                    final = event["item"]["text"]
                if event.get("type") == "turn.completed":
                    completed, usage = True, event.get("usage", {})
                if event.get("type") in {"turn.failed", "error"}:
                    raise ValueError("Codex reported a failed turn")
            if not completed or final is None:
                raise ValueError("Codex turn did not complete")
            payload = json.loads(final)
        elif self.spec.kind == "native_claude":
            events = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line]
            final = next((event for event in reversed(events) if event.get("type") == "result"), None)
            if not final or final.get("is_error"):
                raise ValueError("Claude turn did not complete")
            payload = final.get("structured_output")
            if payload is None:
                payload = json.loads(final.get("result", ""))
            provider_session = final.get("session_id")
            usage = {**final.get("usage", {}), "cost_usd": final.get("total_cost_usd")}
        else:
            envelope = json.loads(raw)
            payload = envelope.get("result", envelope)
            provider_session, usage = None, envelope.get("usage", {})
        return TurnResult(TaskResult.model_validate(payload), provider_session, receipt, usage)


class HarnessRegistry:
    def __init__(self, store, *, codex=None, permission=None, repository=None, protected=()):
        self.store, self.codex, self.permission = store, codex, permission
        self.repository = repository
        self.protected = tuple(protected)
        existing = {spec.id for spec in store.harnesses()}
        for spec in (HarnessSpec(id="codex", kind="native_codex"), HarnessSpec(id="claude", kind="native_claude")):
            if spec.id not in existing:
                store.put_harness(spec)

    def resolve(self, identifier):
        spec = next((s for s in self.store.harnesses() if s.id == identifier), None)
        if spec is None:
            raise ValueError("Unknown harness; no implicit fallback")
        if spec.kind == "acp":
            from .acp_sessions import AcpHarness
            adapter=AcpHarness(spec, permission=self.permission, sandbox=self.sandbox)
        else:
            adapter=NativeHarness(spec, codex=self.codex, sandbox=self.sandbox if spec.kind=='cli_json' else None)
        if __import__('os').name=='nt' and spec.kind in {'acp','cli_json'}:
            from .windows_isolation import SandboxedHarness
            return SandboxedHarness(adapter)
        return adapter

    def sandbox(self, handle, argv, *, provider_home=None):
        from .terminal import sandbox_command
        if self.repository is None:
            raise ValueError('Registry has no repository sandbox boundary')
        executable=NativeHarness(HarnessSpec(id='sandbox',kind='native_codex'),codex=self.codex).executable()
        if provider_home is None:
            import hashlib
            import sys
            key=hashlib.sha256(str(handle.workspace.resolve()).encode()).hexdigest()
            home=self.repository/'.workbench/agents/runtimes'/('cli-'+handle.seat.harness+'-'+key)
            if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (home,*home.parents) if p.is_relative_to(self.repository)):
                raise ValueError('Refusing redirected harness runtime storage')
            home.mkdir(parents=True,exist_ok=True)
            provider_home=home
            shim='import json,subprocess,sys; args=json.loads(sys.argv[1]); raise SystemExit(subprocess.run(args,cwd=sys.argv[2],shell=False).returncode)'
            argv=[sys.executable,'-I','-c',shim,json.dumps(argv),str(handle.workspace)]
        # Transport to a model provider is separate from the seat's tool-network
        # permission. Direct tool requests still pass the permission broker.
        policy=handle.seat.policy.model_copy(update={'network':True})
        handle.repository=self.repository
        handle.runtime_home=provider_home
        return sandbox_command(executable,handle.workspace,policy,self.repository,argv,provider_home=provider_home,protected=self.protected)

    def probes(self):
        return [self.resolve(spec.id).probe() for spec in self.store.harnesses()]
