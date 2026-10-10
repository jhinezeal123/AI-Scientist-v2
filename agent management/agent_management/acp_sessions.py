"""Generic ACP v1/v2 sessions; v2 acceptance never counts as turn completion."""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
from threading import Event, Thread
import time
import uuid

from .harnesses import Capabilities, SessionHandle, TurnResult, RESULT_SCHEMA
from .models import TaskResult
from .processes import ProcessGroup, private_environment, ProcessFailure


class AcpProtocolError(ValueError):
    def __init__(self, method, error):
        super().__init__(f"ACP {method} returned protocol error {error.get('code')}")
        self.diagnostic = error  # Not emitted to the event journal.


class RpcChannel:
    def __init__(self, argv, cwd, timeout, cancelled, handler, started, environment=None):
        if Path(argv[0]).suffix.lower() in {".cmd", ".bat", ".ps1"}:
            raise ValueError("ACP requires a native executable/Node entrypoint, not a shell shim")
        self.proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False, env=environment or private_environment(), start_new_session=os.name != "nt",
            creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0)
        self.group = ProcessGroup(self.proc)
        self.deadline = time.monotonic() + timeout
        self.cancelled, self.handler = cancelled, handler
        self.inbox, self.outbox = queue.Queue(maxsize=256), queue.Queue(maxsize=256)
        self.failed = Event()
        self.pending, self.counter = {}, 0
        self.threads = []
        self.receipt = None
        self.stderr = bytearray()
        def read():
            count = 0
            try:
                while True:
                    line = self.proc.stdout.readline(2_000_001)
                    if not line:
                        break
                    count += len(line)
                    if len(line) > 2_000_000 or count > 8_000_000:
                        self.failed.set()
                        break
                    self.inbox.put_nowait(json.loads(line))
            except (ValueError, queue.Full, OSError):
                self.failed.set()
            finally:
                try:
                    self.inbox.put_nowait(None)
                except queue.Full:
                    self.failed.set()
        def write():
            try:
                while True:
                    data = self.outbox.get()
                    if data is None:
                        break
                    self.proc.stdin.write(data)
                    self.proc.stdin.flush()
            except (OSError, ValueError):
                self.failed.set()
        def stderr():
            try:
                count = 0
                while chunk := self.proc.stderr.read1(8192):
                    count += len(chunk)
                    self.stderr.extend(chunk[:max(0,100000-len(self.stderr))])
                    if count > 2000000:
                        self.failed.set()
                        break
            except OSError:
                pass
        try:
            started(self.proc)
            for target in (read, write, stderr):
                thread = Thread(target=target, daemon=True)
                thread.start()
                self.threads.append(thread)
        except BaseException:
            self.close()
            raise

    def guard(self):
        if self.cancelled():
            raise InterruptedError("ACP turn cancelled")
        if self.failed.is_set():
            raise ValueError("ACP stream exceeded limits or contained invalid JSON")
        if time.monotonic() >= self.deadline:
            raise TimeoutError("ACP turn exceeded its time limit")

    def send(self, payload):
        self.guard()
        data = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        if len(data) > 2_000_000:
            raise ValueError("ACP request exceeds limit")
        try:
            self.outbox.put_nowait(data)
        except queue.Full:
            raise ValueError("ACP output queue is full") from None

    def pump(self):
        self.guard()
        try:
            message = self.inbox.get(timeout=.05)
        except queue.Empty:
            if self.proc.poll() is not None:
                raise RuntimeError("ACP agent exited before turn completion")
            return
        if message is None:
            raise RuntimeError("ACP protocol stream closed")
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise ValueError("Invalid ACP JSON-RPC envelope")
        if "method" in message:
            response = self.handler(message)
            if "id" in message:
                self.send({"jsonrpc": "2.0", "id": message["id"], **response})
        elif "id" in message:
            if len(self.pending) > 100:
                raise ValueError("Too many unsolicited ACP responses")
            self.pending[message["id"]] = message

    def rpc(self, method, params):
        self.counter += 1
        ident = self.counter
        self.send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        while ident not in self.pending:
            self.pump()
        response = self.pending.pop(ident)
        if "error" in response:
            if response["error"].get("code") == -32000:
                raise ValueError("ACP authentication required; sign in explicitly outside the team")
            raise AcpProtocolError(method, response["error"])
        if not isinstance(response.get("result"), dict):
            raise ValueError("Invalid ACP result")
        return response["result"]

    def close(self):
        stopped = self.group.stop()
        try:
            self.outbox.put_nowait(None)
        except queue.Full:
            pass
        for thread in self.threads:
            thread.join(timeout=1)
        self.receipt = {"pid": self.proc.pid, "process_exited": self.proc.poll() is not None,
                        "tree_stopped": stopped, "exit_code": self.proc.returncode}
        self.group.close()
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                stream.close()
            except OSError:
                pass
        return self.receipt


class AcpHarness:
    def __init__(self, spec, *, permission=None, sandbox=None):
        self.spec, self.permission = spec, permission
        self.sandbox = sandbox
        self.negotiated = {}

    def executable(self):
        executable = shutil.which(self.spec.executable) or self.spec.executable
        if not Path(executable).is_file():
            raise ValueError("ACP executable is unavailable; no automatic installation")
        return executable

    @property
    def capabilities(self):
        caps = self.negotiated
        if self.spec.protocol_version == 2:
            session = caps.get("capabilities", {}).get("session")
            return Capabilities(plan=True, tool_approval=True, resume=isinstance(session, dict),
                                list_sessions=isinstance(session, dict), usage=False)
        agent = caps.get("agentCapabilities", {})
        lifecycle = agent.get("sessionCapabilities", {})
        return Capabilities(plan=True, tool_approval=True,
                            resume=bool(agent.get("loadSession")) or isinstance(lifecycle.get("resume"), dict),
                            list_sessions=isinstance(lifecycle.get("list"), dict))

    def probe(self):
        try:
            self.executable()
            ready = self.spec.enabled
        except ValueError:
            ready = False
        return {"id": self.spec.id, "kind": "acp", "ready": ready, "auth": "negotiated_on_start",
                "version": self.spec.protocol_version, "models": self.spec.models,
                "capabilities": asdict(self.capabilities), "attention_required": "Capabilities are negotiated on initialize",
                "isolation": "Client filesystem/terminal disabled; configure a trusted sandboxed agent command"}

    def start(self, seat, workspace):
        if not self.spec.enabled:
            raise ValueError("ACP harness is disabled")
        self.executable()
        return SessionHandle(uuid.uuid4().hex, seat, Path(workspace))

    def resume(self, handle, provider_session):
        if not isinstance(provider_session, str) or not 1 <= len(provider_session) <= 128:
            raise ValueError("Invalid ACP session token")
        # Support is checked against the fresh initialize response before sending a prompt.
        handle.provider_session = provider_session
        return handle

    def fork(self, handle, provider_session):
        raise ValueError("ACP fork is not a negotiated standard capability")

    def interrupt(self, handle):
        handle.interrupted.set()

    def close(self, handle):
        self.interrupt(handle)

    def approve(self, handle, permission_id, decision):
        if self.permission is None:
            raise ValueError("No human permission broker is attached")
        return self.permission.decide(permission_id, decision)

    def initialize(self, channel):
        version = self.spec.protocol_version
        params = {"protocolVersion": version}
        info = {"name": "ai-scientist-teams", "version": "1.0.0"}
        if version == 1:
            params.update(clientInfo=info, clientCapabilities={})
        else:
            params.update(info=info, capabilities={})
        result = channel.rpc("initialize", params)
        if result.get("protocolVersion") != version:
            raise ValueError("ACP protocol negotiation failed; no implicit downgrade")
        self.negotiated = result
        if version == 2 and not isinstance(result.get("capabilities", {}).get("session"), dict):
            raise ValueError("ACP v2 agent does not support session prompting")
        return result

    def send(self, handle, message, *, request_id, timeout, emit, started):
        messages, order = {}, []
        legacy_chunks = []
        foreground = {"stop": None}
        active = {"session": None, "collect": False}
        total = [0]
        def handler(envelope):
            method, params = envelope["method"], envelope.get("params", {})
            if method == "session/request_permission":
                if params.get("sessionId") != active["session"] or self.permission is None:
                    return {"result": {"outcome": {"outcome": "cancelled"}}}
                decision = self.permission.request(handle, params, channel.guard)
                return {"result": {"outcome": decision}}
            if method == "session/update":
                if params.get("sessionId") != active["session"] or not active["collect"]:
                    return {}
                update = params.get("update", {})
                kind = update.get("sessionUpdate")
                emit(json.dumps({"type": "acp_update", "update": update}, ensure_ascii=False) + "\n")
                if kind == "state_update" and update.get("state") == "idle" and update.get("stopReason"):
                    foreground["stop"] = update["stopReason"]
                if kind in {"agent_message", "agent_message_chunk"}:
                    content = update.get("content", [])
                    parts = content if isinstance(content, list) else [content]
                    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict) and part.get("type") == "text")
                    total[0] += len(text.encode())
                    if total[0] > 2_000_000:
                        raise ValueError("ACP text output exceeded its limit")
                    if self.spec.protocol_version == 1:
                        legacy_chunks.append(text)
                    else:
                        ident = update.get("messageId")
                        if not isinstance(ident, str):
                            raise ValueError("ACP v2 message lacks its identity")
                        if ident not in messages:
                            messages[ident] = ""
                            order.append(ident)
                        if kind == "agent_message":
                            # Omitted content does not change an existing message.
                            if "content" in update:
                                messages[ident] = text
                        else:
                            messages[ident] += text
                return {}
            return {"error": {"code": -32601, "message": "Client filesystem/terminal capability disabled"}}
        environment = private_environment()
        if self.spec.managed_home:
            from .dsh import session_home
            environment['DSH_HOME'] = str(session_home(Path(self.spec.managed_home), handle.workspace))
            temporary=Path(environment['DSH_HOME'])/'tmp'
            temporary.mkdir(exist_ok=True)
            environment.update(TEMP=str(temporary),TMP=str(temporary),TMPDIR=str(temporary))
        argv = [self.executable(), *self.spec.args]
        if self.sandbox:
            argv = self.sandbox(handle, argv, provider_home=environment.get('DSH_HOME'))
        channel = RpcChannel(argv, handle.workspace, timeout,
                             handle.interrupted.is_set, handler, started, environment)
        try:
            initialized = self.initialize(channel)
            emit(json.dumps({"type": "capabilities", "protocol": self.spec.protocol_version,
                             "capabilities": asdict(self.capabilities)}) + "\n")
            if handle.provider_session:
                if not self.capabilities.resume:
                    raise ValueError("ACP resume is unsupported by this agent")
                active["session"] = handle.provider_session
                params = {"sessionId": handle.provider_session, "cwd": str(handle.workspace.resolve()), "mcpServers": []}
                if self.spec.protocol_version == 2:
                    params["replayFrom"] = {"type": "start"}
                    session = channel.rpc("session/resume", params)
                else:
                    method = "session/load" if initialized.get("agentCapabilities", {}).get("loadSession") else "session/resume"
                    session = channel.rpc(method, params)
            else:
                session = channel.rpc("session/new", {"cwd": str(handle.workspace.resolve()), "mcpServers": []})
                active["session"] = session.get("sessionId")
            if not isinstance(active["session"], str) or not active["session"]:
                raise ValueError("ACP session identity is missing")
            if handle.seat.model:
                options = session.get("configOptions", [])
                model_option = next((o for o in options if o.get("category") == "model"), None)
                if model_option is None:
                    raise ValueError("Agent does not advertise a model configuration option")
                def values(options):
                    for option in options:
                        if isinstance(option, dict):
                            if "value" in option:
                                yield option["value"]
                            yield from values(option.get("options", []))
                allowed = set(values(model_option.get("options", [])))
                if handle.seat.model not in allowed:
                    raise ValueError("Model is not advertised by this ACP session")
                channel.rpc("session/set_config_option", {"sessionId": active["session"],
                    "configId": model_option["id"], "value": handle.seat.model})
            active["collect"] = True
            instruction = message + "\nReturn only JSON matching this schema:\n" + json.dumps(RESULT_SCHEMA)
            accepted = channel.rpc("session/prompt", {"sessionId": active["session"],
                "prompt": [{"type": "text", "text": instruction}]})
            if self.spec.protocol_version == 2:
                if not isinstance(accepted.get("messageId"), str):
                    raise ValueError("ACP v2 prompt was not acknowledged with a messageId")
                while foreground["stop"] is None:
                    channel.pump()
                stop = foreground["stop"]
            else:
                stop = accepted.get("stopReason")
            if stop != "end_turn":
                raise ValueError("ACP foreground turn did not finish successfully")
            text = "".join(legacy_chunks) if self.spec.protocol_version == 1 else "\n".join(messages[i] for i in order)
            result = TaskResult.model_validate_json(text)
            if self.spec.protocol_version == 2 or "close" in initialized.get("agentCapabilities", {}).get("sessionCapabilities", {}):
                channel.rpc("session/close", {"sessionId": active["session"]})
        except BaseException as exc:
            receipt = channel.close()
            handle.stop_receipt = receipt
            exc.diagnostic = getattr(exc, 'diagnostic', None) or {'stderr':bytes(channel.stderr)}
            if isinstance(exc, (InterruptedError, TimeoutError)) or not receipt["tree_stopped"]:
                raise ProcessFailure(str(exc), receipt, cancelled=isinstance(exc, InterruptedError), diagnostic=exc.diagnostic) from None
            raise
        else:
            receipt = channel.close()
            handle.stop_receipt = receipt
            if not receipt["tree_stopped"]:
                raise ProcessFailure("ACP process tree could not be confirmed stopped", receipt)
            return TurnResult(result, active["session"], receipt)
