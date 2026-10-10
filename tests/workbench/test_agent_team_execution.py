import importlib
import json
import pathlib
import subprocess
import sys
import time

import pytest

from ai_scientist.workbench.runtime import _agent_gateway_class

PACKAGE = _agent_gateway_class().__module__.rsplit(".", 1)[0]
models = importlib.import_module(PACKAGE + ".models")
processes = importlib.import_module(PACKAGE + ".processes")
harnesses = importlib.import_module(PACKAGE + ".harnesses")
acp = importlib.import_module(PACKAGE + ".acp_sessions")
AgentStore = importlib.import_module(PACKAGE + ".store").AgentStore
Platform = importlib.import_module(PACKAGE + ".orchestrator").TeamPlatform


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src/demo.py").write_text("original\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "src"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@localhost", "commit", "-m", "base"], capture_output=True, check=True)
    return tmp_path


def test_bounded_writer_deadline_and_process_tree(tmp_path):
    fixture = tmp_path / "slow.py"
    fixture.write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\ntime.sleep(60)\n")
    start = time.monotonic()
    with pytest.raises(processes.ProcessFailure) as result:
        processes.run_process([sys.executable, str(fixture)], tmp_path, b"x" * 1_000_000,
            timeout=.25, cancelled=lambda: False, emit=lambda text: None)
    assert time.monotonic() - start < 8
    assert result.value.receipt["process_exited"] and result.value.receipt["tree_stopped"]

def test_native_action_contract_keeps_local_tools_disabled(tmp_path,monkeypatch):
    captured={}
    def wire(argv,cwd,body,**kwargs):
        captured.update(argv=argv,prompt=body.decode())
        result={'summary':json.dumps({'action':'exec','command':'python source/workload.py'}),
                'files':[],'checks':[],'handoff':''}
        events=[{'type':'item.completed','item':{'type':'agent_message','text':json.dumps(result)}},
                {'type':'turn.completed','usage':{}}]
        return '\n'.join(json.dumps(e) for e in events).encode(),{'tree_stopped':True}
    monkeypatch.setattr(harnesses,'run_process',wire)
    adapter=harnesses.NativeHarness(models.HarnessSpec(id='codex',kind='native_codex',executable=sys.executable))
    handle=adapter.start(models.AgentSpec(id='draft'),tmp_path)
    result=adapter.send(handle,'Return an exec action for the authorized session',request_id='node',timeout=5,
                        emit=lambda _:None,started=lambda _:None)
    assert json.loads(result.result.summary)['action']=='exec'
    assert 'structured remote actions as JSON' in captured['prompt']
    assert 'Do not call local tools' in captured['prompt']
    assert 'independently create research sessions' in captured['prompt']
    for tool in ('shell_tool','unified_exec','apps','computer_use','browser_use'):
        index=captured['argv'].index(tool)
        assert captured['argv'][index-1]=='--disable'
    assert 'sandbox_mode="read-only"' in captured['argv']


@pytest.mark.parametrize("version", [1, 2])
def test_acp_prompt_lifecycle_and_capabilities(tmp_path, version):
    fixture = tmp_path / "acp.py"
    fixture.write_text('''import json,sys,time
def send(value): print(json.dumps(value),flush=True)
def update(session,value): send({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':session,'update':value}})
for line in sys.stdin:
 msg=json.loads(line); method=msg['method']; params=msg.get('params',{}); result={}
 if method=='initialize':
  version=params['protocolVersion']; result={'protocolVersion':version,'authMethods':[{'id':'existing-login'}]}
  if version==2: result['capabilities']={'session':{}}
  else: result['agentCapabilities']={'loadSession':True}
 elif method=='session/new':result={'sessionId':'s1'}
 elif method=='session/prompt':
  text=json.dumps({'summary':'ok','files':[],'checks':[],'handoff':''})
  if version==2:
   send({'jsonrpc':'2.0','id':msg['id'],'result':{'messageId':'accepted'}})
   time.sleep(.2)
   update('s1',{'sessionUpdate':'agent_message','messageId':'answer','content':[{'type':'text','text':'stale'}]})
   update('s1',{'sessionUpdate':'agent_message','messageId':'answer','content':[{'type':'text','text':text}]})
   update('s1',{'sessionUpdate':'state_update','state':'idle','stopReason':'end_turn'})
   continue
  update('s1',{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':text}})
  result={'stopReason':'end_turn'}
 send({'jsonrpc':'2.0','id':msg['id'],'result':result})
''')
    adapter = acp.AcpHarness(models.HarnessSpec(id="fixture", kind="acp", executable=sys.executable,
                            args=[str(fixture)], protocol_version=version))
    handle = adapter.start(models.AgentSpec(id="lead"), tmp_path)
    start = time.monotonic()
    result = adapter.send(handle, "test", request_id="test", timeout=5,
                          emit=lambda text: None, started=lambda proc: None)
    assert result.result.summary == "ok" and result.receipt["tree_stopped"]
    assert adapter.capabilities.resume
    if version == 2:
        assert time.monotonic() - start >= .2


def test_acp_v2_ack_without_idle_is_not_completed(tmp_path):
    fixture = tmp_path / "acp.py"
    fixture.write_text('''import json,sys,time
for line in sys.stdin:
 m=json.loads(line)
 if m['method']=='initialize':r={'protocolVersion':2,'capabilities':{'session':{}}}
 elif m['method']=='session/new':r={'sessionId':'s1'}
 else:r={'messageId':'accepted'}
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':r}),flush=True)
''')
    adapter = acp.AcpHarness(models.HarnessSpec(id="fixture", kind="acp", executable=sys.executable,
                            args=[str(fixture)], protocol_version=2))
    handle = adapter.start(models.AgentSpec(id="lead"), tmp_path)
    with pytest.raises(processes.ProcessFailure, match="time limit") as result:
        adapter.send(handle, "test", request_id="test", timeout=.5,
                     emit=lambda text: None, started=lambda proc: None)
    assert result.value.receipt["tree_stopped"]


class FixtureRegistry:
    def __init__(self, fixture):
        self.fixture = fixture
    def resolve(self, identifier):
        return harnesses.NativeHarness(models.HarnessSpec(id=identifier, kind="cli_json",
            executable=sys.executable, args=[str(self.fixture)]))


def wait_finished(platform, rig_id, count):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        snapshot = platform.store.snapshot(rig_id)
        if len(snapshot["tasks"]) == count and all(t["state"] in {"DONE", "FAILED", "UNKNOWN", "CANCELLED"} for t in snapshot["tasks"]):
            return snapshot
        time.sleep(.05)
    pytest.fail("Team did not finish: " + json.dumps(snapshot))


def test_structured_stage_excludes_workspace_and_other_workflow_chat(repository):
    fixture = repository / "structured.py"
    fixture.write_text('''import json,sys
request=json.load(sys.stdin)
message=json.loads(request['prompt'].split('\\n',1)[1])
assert message['files']==[], message['files']
assert message['messages']==[], message['messages']
assert 'current-workflow' in message['task']
print(json.dumps({'result':{'summary':'isolated stage inputs','files':[],'checks':[],'handoff':''}}))
''')
    queue = AgentStore(repository / ".workbench/control.sqlite")
    platform = Platform(queue, repository, registry=FixtureRegistry(fixture))
    try:
        platform.create('stages', models.RigSpec.model_validate(models.templates()[-1]))
        queue.send('stages', 'proposal', '*', 'Old workflow requires human approval')
        platform.enqueue('stages', 'ideation', 'stage-1', models.TaskRequest(instruction='current-workflow', structured_only=True))
        platform.start('stages')
        snapshot = wait_finished(platform, 'stages', 1)
        assert snapshot['tasks'][0]['state']=='DONE', snapshot
        assert snapshot['sessions'][0]['stop_receipt']['tree_stopped']
    finally:
        platform.close()


def test_four_seat_pipeline_checkpoint_restart_and_no_replay(repository):
    fixture = repository / "fixture.py"
    fixture.write_text('''import json,sys
request=json.load(sys.stdin)
message=json.loads(request['prompt'].split('\\n',1)[1])
role=message['role']
files=[{'path':'src/demo.py','content':'changed\\n'}] if role=='builder' else []
print(json.dumps({'result':{'summary':role,'files':files,'checks':[],'handoff':'handoff '+role}}))
''')
    registry = FixtureRegistry(fixture)
    queue = AgentStore(repository / ".workbench/control.sqlite")
    platform = Platform(queue, repository, registry=registry)
    spec = models.RigSpec.model_validate(models.templates()[1])
    platform.create("pipeline", spec)
    dependency = None
    ids = []
    for seat in ("lead", "builder", "qa", "reviewer"):
        task = platform.enqueue("pipeline", seat, "request-" + seat,
            models.TaskRequest(instruction="Do your role"), depends_on=dependency)
        ids.append(task["id"])
        dependency = task["id"]
    platform.start("pipeline")
    snapshot = wait_finished(platform, "pipeline", 4)
    platform.pause("pipeline")
    assert [t["state"] for t in snapshot["tasks"]] == ["DONE"] * 4, snapshot
    assert len(snapshot["sessions"]) == 4
    assert (repository / "src/demo.py").read_text() == "original\n"
    reviewer = platform.workspaces.path("pipeline", "reviewer")
    assert (reviewer / "src/demo.py").read_text() == "changed\n"
    saved = platform.snapshot("pipeline")
    platform.close()
    restarted = Platform(queue, repository, registry=registry)
    assert restarted.store.snapshot("pipeline")["tasks"][0]["id"] == ids[0]
    replay = restarted.enqueue("pipeline", "lead", "request-lead", models.TaskRequest(instruction="Do your role"))
    assert replay["id"] == ids[0] and replay["state"] == "DONE"
    restarted.restore("pipeline", saved["id"])
    restarted.start("pipeline")
    time.sleep(.3)
    assert len(restarted.store.snapshot("pipeline")["sessions"]) == 4
    restarted.close()
