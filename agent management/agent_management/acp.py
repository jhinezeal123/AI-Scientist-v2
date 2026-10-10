"""Bounded ACP v1 stdio bridge for an explicitly configured local agent command.

The bridge deliberately advertises no client filesystem/terminal capabilities. It
denies agent-initiated requests and permission prompts instead of bypassing the
existing human-approval workflow. ACP v2 and interactive login are not supported
here; expand via a tested SDK/client before advertising those capabilities.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import signal
import subprocess
from threading import Thread
import time

from ai_scientist.workbench.agents.contracts import (
    RuntimeCancelled, RuntimeProgress, RuntimeResult, RuntimeUncertain,
)

_MAX_LINE = 2_000_000


class AcpStdioRuntime:
    def __init__(self, executable: str, args: tuple[str, ...] = (), *, model: str | None = None):
        if not executable or any("\x00" in x for x in (executable, *args)):
            raise ValueError("Invalid ACP executable or arguments")
        if model is not None:
            raise ValueError("ACP v1 model switching is not yet implemented; select the model in the agent's own config")
        self.executable, self.args = executable, args

    @staticmethod
    def _stop(proc: subprocess.Popen) -> bool:
        if proc.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   capture_output=True, timeout=5)
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
            except (OSError, subprocess.SubprocessError):
                try:
                    proc.kill()
                except OSError:
                    pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return proc.poll() is not None

    def run(self, request, progress, cancelled) -> RuntimeResult:
        if cancelled():
            raise RuntimeCancelled("ACP request cancelled before start")
        cwd = Path(request.workdir)
        if not cwd.is_dir():
            raise ValueError("ACP workspace does not exist")
        args = [self.executable, *self.args]
        proc = subprocess.Popen(
            args, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False,
            **({"start_new_session": True} if os.name != "nt" else
               {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}),
        )
        inbox: queue.Queue = queue.Queue(maxsize=256)
        overflow = [False]

        def reader():
            try:
                while True:
                    line = proc.stdout.readline(_MAX_LINE + 1)
                    if not line:
                        break
                    if len(line) > _MAX_LINE:
                        overflow[0] = True
                        break
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except (ValueError, UnicodeError):
                        overflow[0] = True
                        break
                    try:
                        inbox.put_nowait(msg)
                    except queue.Full:
                        overflow[0] = True
                        break
            finally:
                try:
                    inbox.put_nowait(None)
                except queue.Full:
                    overflow[0] = True

        def drain_stderr():
            # Drain without retaining potentially sensitive agent stderr.
            while proc.stderr.read(65536):
                pass

        Thread(target=reader, daemon=True).start()
        Thread(target=drain_stderr, daemon=True).start()
        deadline = time.monotonic() + max(1, request.timeout_seconds)
        pending = {}
        next_id = [0]
        texts = []
        session_id = None
        completed = False
        progress(RuntimeProgress("agent", "Starting configured ACP v1 agent"))

        def send(payload):
            proc.stdin.write((json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode())
            proc.stdin.flush()

        def receive():
            while True:
                if cancelled():
                    raise RuntimeCancelled("ACP request cancelled")
                if overflow[0]:
                    raise ValueError("ACP event exceeded limits or was invalid")
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("ACP agent exceeded its time limit")
                try:
                    msg = inbox.get(timeout=min(0.1, left))
                except queue.Empty:
                    if proc.poll() is not None and inbox.empty():
                        raise RuntimeError("ACP agent exited before completing the turn")
                    continue
                if msg is None:
                    raise RuntimeError("ACP agent closed the protocol stream")
                if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
                    raise ValueError("Invalid ACP JSON-RPC envelope")
                if "method" in msg and "id" in msg:
                    # Always deny side-effecting client requests; never silently grant
                    # permissions to an agent working inside approved research scope.
                    method = msg["method"]
                    if method == "session/request_permission":
                        send({"jsonrpc": "2.0", "id": msg["id"],
                              "result": {"outcome": {"outcome": "cancelled"}}})
                    else:
                        send({"jsonrpc": "2.0", "id": msg["id"],
                              "error": {"code": -32601, "message": "Client capability not enabled"}})
                    continue
                if msg.get("method") == "session/update":
                    params = msg.get("params", {})
                    update = params.get("update", {}) if isinstance(params, dict) else {}
                    if isinstance(update, dict) and update.get("sessionUpdate") == "agent_message_chunk":
                        part = update.get("content", {})
                        if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                            texts.append(part["text"])
                            if sum(len(x) for x in texts) > min(_MAX_LINE, request.max_output_bytes):
                                raise ValueError("ACP output exceeded the configured size limit")
                            progress(RuntimeProgress("agent", "ACP agent returned a text chunk"))
                    continue
                if "id" in msg:
                    pending[msg["id"]] = msg
                    return

        def rpc(method, params):
            ident = next_id[0]
            next_id[0] += 1
            send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
            while ident not in pending:
                receive()
            message = pending.pop(ident)
            if "error" in message:
                raise RuntimeError(f"ACP {method} returned a protocol error")
            result = message.get("result")
            if not isinstance(result, dict):
                raise ValueError(f"ACP {method} returned invalid result")
            return result

        try:
            initialized = rpc("initialize", {
                "protocolVersion": 1, "clientCapabilities": {},
                "clientInfo": {"name": "ai-scientist-workbench", "version": "0.1.0"},
            })
            if initialized.get("protocolVersion") != 1:
                raise RuntimeError("This adapter only supports ACP v1")
            if initialized.get("authMethods"):
                raise RuntimeError("ACP agent needs interactive authentication; sign in separately")
            session = rpc("session/new", {"cwd": str(cwd.resolve()), "mcpServers": []})
            session_id = session.get("sessionId")
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("ACP agent returned no session ID")
            result = rpc("session/prompt", {
                "sessionId": session_id, "prompt": [{"type": "text", "text": request.prompt}],
            })
            if result.get("stopReason") != "end_turn":
                raise RuntimeError("ACP turn did not complete successfully")
            completed = True
            return RuntimeResult(text="".join(texts), files={}, session_id=session_id)
        finally:
            if not self._stop(proc):
                # Prefer UNKNOWN over a fabricated completion or safe cancellation.
                raise RuntimeUncertain("ACP process could not be confirmed stopped")
