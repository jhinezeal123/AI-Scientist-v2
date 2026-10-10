"""MVP5 gateway: one alias, durable coordination and opt-in REST."""
import asyncio
import importlib
import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_scientist.workbench.agents.contracts import RuntimeRequest, RuntimeResult
from ai_scientist.workbench.runtime import _agent_gateway_class, load_runtime
from ai_scientist.workbench.worker import RuntimeWorker

Gateway = _agent_gateway_class()
Package = importlib.import_module(Gateway.__module__.rsplit(".", 1)[0])


class FakeCodex:
    def __init__(self):
        self.calls = []

    def run(self, request, progress, cancelled):
        self.calls.append((request, progress, cancelled))
        return RuntimeResult(text=json.dumps({
            "summary": "ok", "interpretation": "test", "limitations": [],
            "suggested_next": [], "evidence_refs": []}), session_id="legacy")


def test_default_load_runtime_one_alias_no_side_effects(tmp_path):
    config = SimpleNamespace(
        codex_executable=tmp_path / "codex", codex_model="fixture",
        codex_reasoning_effort="high", workspace_root=tmp_path)
    loaded = load_runtime(config)
    assert isinstance(loaded.runtime, Gateway)
    assert loaded.runtime.spec.for_role("mvp0_plan").kind == "native_codex"
    assert loaded.runtime.spec.for_role("mvp0_working").kind == "native_codex"
    assert not (tmp_path / ".workbench").exists()


def test_worker_preserves_contract_and_request_identity(tmp_path):
    legacy = FakeCodex()
    gateway = Gateway(legacy, tmp_path)
    async def run():
        worker = RuntimeWorker(gateway, tmp_path / "runtime.json")
        request = RuntimeRequest("report-1", "mvp0_report", "original prompt", tmp_path)
        result, payload = await worker.run(request)
        assert payload.summary == "ok" and result.session_id == "legacy"
        assert len(legacy.calls) == 1 and legacy.calls[0][0] is request
        await worker.close(1)
    asyncio.run(run())


def test_explicit_role_seat_provider_and_strict_config(tmp_path):
    file = tmp_path / "profiles.json"
    file.write_text(json.dumps({
        "version": 1,
        "providers": {"deepseek": {"kind": "acp", "executable": "dsh",
                                  "args": ["--profile", "acp"]}},
        "seats": {"lead": {"provider": "codex"}, "builder": {"provider": "deepseek"}},
        "default_seat": "lead",
        "role_seats": {"mvp0_working": "builder"},
    }))
    alias = Gateway(FakeCodex(), tmp_path, spec_path=file)
    assert alias.spec.for_role("mvp0_plan").name == "codex"
    assert alias.spec.for_role("mvp0_working").name == "deepseek"
    assert alias.capabilities()[0]["kind"] == "native_codex"
    with pytest.raises(ValueError, match="role or seat"):
        Package.GatewaySpec.from_dict({"role_seats": {"no_such_role": "default"}})
    with pytest.raises(ValueError, match="unknown provider"):
        Package.GatewaySpec.from_dict({"seats": {"default": {"provider": "missing"}}})


def test_durable_queue_idempotency_lease_and_unknown(tmp_path):
    alias = Gateway(FakeCodex(), tmp_path)
    alias.create_rig("team", seats=["default"])
    a = alias.enqueue("team", "default", "id-1", {"task": "build"})
    assert alias.enqueue("team", "default", "id-1", {"task": "build"})["id"] == a["id"]
    with pytest.raises(ValueError, match="different task"):
        alias.enqueue("team", "default", "id-1", {"task": "changed"})
    b = alias.enqueue("team", "default", "id-2", {"task": "review"}, depends_on=a["id"])
    claim = alias.claim("team", "default")
    assert claim["id"] == a["id"]
    assert alias.claim("team", "default") is None
    with pytest.raises(ValueError, match="Lease invalid"):
        alias.finish(a["id"], "bad-token")
    alias.finish(a["id"], claim["lease_token"], result={"passed": True})
    assert alias.claim("team", "default")["id"] == b["id"]
    with sqlite3.connect(tmp_path / ".workbench" / "agent-management.sqlite") as con:
        con.execute("UPDATE tasks SET lease_until='2000-01-01T00:00:00+00:00' WHERE id=?", (b["id"],))
    assert alias.claim("team", "default") is None
    assert alias.snapshot("team")["tasks"][1]["state"] == "UNKNOWN"


def test_messages_and_disabled_by_default_control_api(tmp_path, monkeypatch):
    alias = Gateway(FakeCodex(), tmp_path)
    app = FastAPI()
    from _ai_scientist_agent_management.http_api import create_router
    app.include_router(create_router())
    app.state.runtime = SimpleNamespace(runtime=alias)
    with TestClient(app) as client:
        assert client.get("/api/agent-management/providers").status_code == 404
        monkeypatch.setenv("AI_SCIENTIST_AGENT_CONTROL_TOKEN", "fixture-secret")
        assert client.get("/api/agent-management/providers").status_code == 401
        headers = {"Authorization": "Bearer fixture-secret"}
        assert client.post("/api/agent-management/rigs", headers=headers,
                           json={"rig_id": "team", "seats": ["default"]}).status_code == 200
        assert client.post("/api/agent-management/rigs/team/messages", headers=headers,
                           json={"sender": "default", "recipient": "*",
                                 "body": "Review"}).status_code == 200
        inbox = client.get("/api/agent-management/rigs/team/seats/default/inbox", headers=headers)
        assert inbox.json()[0]["body"] == "Review"
        assert client.post("/api/agent-management/rigs/team/tasks", headers=headers,
            json={"seat": "default", "request_id": "test", "task": {"title": "review"}}).status_code == 200


def test_acp_v1_stdio_fixture(tmp_path):
    import sys
    script = tmp_path / "fake_agent.py"
    script.write_text(
        "import json,sys\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line)\n"
        " method=m.get('method')\n"
        " if method=='initialize': r={'protocolVersion':1,'agentCapabilities':{},'authMethods':[]}\n"
        " elif method=='session/new': r={'sessionId':'session-1'}\n"
        " elif method=='session/prompt':\n"
        "  print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':"
        "{'sessionId':'session-1','update':{'sessionUpdate':'agent_message_chunk',"
        "'content':{'type':'text','text':'fixture'}}}}),flush=True)\n"
        "  r={'stopReason':'end_turn'}\n"
        " else: r={}\n"
        " print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':r}),flush=True)\n")
    from _ai_scientist_agent_management.acp import AcpStdioRuntime
    result = AcpStdioRuntime(sys.executable, ("-u", str(script))).run(
        RuntimeRequest("one", "mvp0_report", "prompt", tmp_path, timeout_seconds=5),
        lambda event: None, lambda: False)
    assert result.text == "fixture" and result.session_id == "session-1"
