"""Optional real n8n QA; isolated instance, no provider or Kaggle spending.

N8N_QA_ROOT points to the isolated profile whose workflows target port 8001.
"""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace
from urllib.request import Request, urlopen

from fastapi import FastAPI
import pytest
import uvicorn

from ai_scientist.workbench.agents.contracts import RuntimeRequest
from ai_scientist.workbench.n8n_api import create_n8n_router
from ai_scientist.workbench.n8n_client import N8nClient
from ai_scientist.workbench.ssh_terminal import AgentTerminalBridge
from ai_scientist.workbench.stage_runtime import StageRuntime
from tests.workbench.test_n8n_workflows import setup, FixtureAdapter, repository

pytestmark = pytest.mark.skipif(not os.environ.get('N8N_QA_ROOT'), reason='Requires isolated local n8n')


def test_actual_n8n_canvas_human_gates_and_remote_action_loop(repository, monkeypatch):
    root = Path(os.environ['N8N_QA_ROOT'])
    with sqlite3.connect(root/'profile/.n8n/database.sqlite') as con:
        baseline = con.execute('SELECT COALESCE(MAX(CAST(id AS INTEGER)),0) FROM execution_entity').fetchone()[0]
    owner, project, identity, _, adapter = setup(repository, max_runs=2)
    class DialoguePlanner(FixtureAdapter):
        def send(self, handle, message, **kwargs):
            if not self.calls:
                self.calls.append(handle.seat.model)
                handle.stop_receipt={'tree_stopped':True,'process_exited':True}
                return SimpleNamespace(result=SimpleNamespace(summary=json.dumps({
                    'needs_clarification':True,'questions':['Which checksum inputs should be covered?'],
                    'paraphrase':'Need concrete checksum scope'}),files=[]),receipt=handle.stop_receipt)
            return super().send(handle,message,**kwargs)
    adapter=DialoguePlanner()
    owner.gateway._harness_catalog.resolve=lambda _:adapter
    async def variant(project, parent, request, title, text, changes, mode, output, research, tags, benchmark):
        return owner.projects.save_idea(project, text, title, mode, output, research, tags, benchmark)
    owner.planner.create_variant = variant
    owner.client = N8nClient(repository, base_url='http://127.0.0.1:5680')
    owner.client.token = (root/'bridge-token.txt').read_text().strip()
    owner.agent_turns.client = owner.client
    owner.callbacks.client = owner.client
    monkeypatch.setenv('AI_SCIENTIST_AGENT_CONTROL_TOKEN', 'fixture-only-key')
    @asynccontextmanager
    async def lifespan(_):
        yield
        await owner.close()
    app = FastAPI(lifespan=lifespan)
    app.state.runtime = SimpleNamespace(runtime=owner.gateway)
    app.state.store = owner.projects
    app.state.research_workflows = owner
    app.include_router(create_n8n_router())
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8001, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    def api(path, body=None):
        req = Request('http://127.0.0.1:8001/api/agent-management'+path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': 'Bearer fixture-only-key', 'Content-Type': 'application/json'})
        with urlopen(req, timeout=10) as response:
            return json.load(response)

    def until(operation, seconds=90):
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            value = operation()
            if value:
                return value
            time.sleep(.1)
        raise AssertionError('Live n8n operation did not finish')

    base = f'/projects/{project}/workflows/{identity}'
    try:
        until(lambda: server.started, 10)
        assert owner.client.status()['ready']
        api(base+'/start', {})
        gates = []
        for iteration in range(2):
            for stage in ('ideation', 'approval', 'run_approval'):
                pending = until(lambda: next((v for v in owner.store.inputs(project, identity)
                                               if v['stage'] == stage and v['state'] == 'PENDING'), None))
                assert owner.working.admissions == iteration
                gates.append(stage)
                if stage=='approval' and iteration==0:
                    from urllib.error import HTTPError
                    import uuid
                    assert pending['prompt']['approval_allowed'] is False
                    with pytest.raises(HTTPError):
                        api(base+'/inputs/'+pending['id'],{'result':{'approve':True,'reason':'Try bypass clarification'}})
                    for round in range(2):
                        api(base+'/inputs/'+pending['id'],{'result':{'message':'Cover empty and Unicode checksum inputs',
                            'request_id':uuid.uuid4().hex}})
                        pending=until(lambda:next((v for v in owner.store.inputs(project,identity)
                            if v['stage']=='approval' and v['state']=='PENDING' and v['prompt'].get('proposal_round')==round+1),None))
                        assert pending['prompt']['approval_allowed'] and owner.working.admissions==0
                api(base+'/inputs/'+pending['id'], {'result': {'title': 'Checksum', 'text': 'Verify checksum'}
                    if stage == 'ideation' else {'approve': True, 'reason': 'Reviewed exact candidate'}})
        until(lambda: owner.store.get(project, identity)['state']['status'] == 'DONE')
        assert gates == ['ideation', 'approval', 'run_approval']*2
        assert adapter.calls == ['copied-model']*4
        assert owner.working.admissions == 2
        row = owner.store.get(project, identity)
        assert row['state']['n8n_execution_id']
        until(lambda: all(j['status'] == 'DONE' for j in owner.store.get(project, identity)['state']['step_jobs'].values()))

        # A remote ticket uses the same real n8n agent canvas, including write/read.
        owner.store.change(project, identity, lambda s: s.update(status='RUNNING'))
        commands, requests = [], []
        def terminal(action, **kwargs):
            requests.append((action, kwargs))
            return {'returncode': 0, 'text': '4/4 assertions passed'}
        remote_calls = []
        class RemoteAdapter(FixtureAdapter):
            def send(self, handle, message, **kwargs):
                prompt = json.loads(message)['input']
                remote_calls.append(prompt)
                actions = [
                    {'action': 'exec', 'command': 'python source/checksum.py', 'timeout': 2},
                    {'action': 'write', 'path': 'output/result.txt', 'data': 'dmVyaWZpZWQ='},
                    {'action': 'read', 'path': 'output/result.txt'},
                    {'action': 'finish', 'result': {'succeeded': True, 'summary': 'verified',
                                                  'limitations': [], 'output_files': []}},
                ]
                handle.stop_receipt = {'tree_stopped': True, 'process_exited': True}
                return SimpleNamespace(result=SimpleNamespace(summary=json.dumps(actions[len(remote_calls)-1]), files=[]), receipt=handle.stop_receipt)
        owner.gateway._harness_catalog.resolve = lambda _: RemoteAdapter()
        workdir = repository/'working'
        bridge = AgentTerminalBridge(SimpleNamespace(request=terminal), workdir, on_command=commands.append)
        try:
            result = StageRuntime(owner, project, identity).run(
                RuntimeRequest('run', 'mvp0_working', 'Verify checksum', workdir, timeout_seconds=80),
                lambda _: None, lambda: False)
            assert json.loads(result.text)['succeeded']
            assert len(commands) == 1
            assert [a for a, _ in requests] == ['exec', 'write', 'read']
            assert 'timeout' not in requests[1][1] and 'timeout' not in requests[2][1]
            assert bridge.token not in json.dumps(remote_calls)
        finally:
            bridge.close()
        # Actual n8n ticket loop forwards files as images, never base64 text.
        from PIL import Image
        image = repository/'vision.png'
        Image.new('RGB',(40,40),'red').save(image)
        seen = []
        class VisionAdapter(FixtureAdapter):
            def send(self,handle,message,**kwargs):
                seen.extend(kwargs['images'])
                assert seen[0].read_bytes()==image.read_bytes()
                assert 'data:image' not in message
                handle.stop_receipt={'tree_stopped':True,'process_exited':True}
                return SimpleNamespace(result=SimpleNamespace(summary='{"seen":true}',files=[]),receipt=handle.stop_receipt)
        owner.gateway._harness_catalog.resolve=lambda _:VisionAdapter()
        result=StageRuntime(owner,project,identity).invoke('vision',{'task':'Check actual image'},
            {'type':'object','required':['seen'],'properties':{'seen':{'const':True}}},timeout=30,images=(image,))
        assert result['seen'] and len(seen)==1
        # Actual persisted n8n execution outcomes, not just backend state.
        db = root/'profile/.n8n/database.sqlite'
        def executions_done():
            with sqlite3.connect(db) as con:
                rows = con.execute('SELECT workflowId,status FROM execution_entity WHERE CAST(id AS INTEGER)>?', (baseline,)).fetchall()
            return rows if len(rows) >= 4 and all(status == 'success' for _, status in rows) else None
        executions = until(executions_done, 20)
        assert {name for name, _ in executions} == {'workbenchResearch', 'workbenchAgent'}
        assert owner.gateway._platform is None
        # A rejected human proposal resumes the callback Wait with failure,
        # stops the actual n8n execution and never admits another run.
        import uuid
        from ai_scientist.workbench.workflow_models import WorkflowSpec
        owner.gateway._harness_catalog.resolve=lambda _:adapter
        owner.store.change(project, identity, lambda s: s.update(status='DONE'))
        rejected = uuid.uuid4().hex
        owner.create(project, rejected, WorkflowSpec.model_validate(row['spec']))
        rejected_base = f'/projects/{project}/workflows/{rejected}'
        api(rejected_base+'/start', {})
        idea = until(lambda: next((v for v in owner.store.inputs(project, rejected)
                                    if v['stage']=='ideation' and v['state']=='PENDING'), None))
        api(rejected_base+'/inputs/'+idea['id'], {'result': {'title':'Rejected candidate','text':'Do not execute'}})
        approval = until(lambda: next((v for v in owner.store.inputs(project, rejected)
                                        if v['stage']=='approval' and v['state']=='PENDING'), None))
        api(rejected_base+'/inputs/'+approval['id'], {'result': {'approve':False,'reason':'Rejected in QA'}})
        until(lambda: owner.store.get(project,rejected)['state']['status']=='PAUSED')
        rejected_execution=owner.store.get(project,rejected)['state']['n8n_execution_id']
        def failed_execution():
            with sqlite3.connect(db) as con:
                saved=con.execute('SELECT status FROM execution_entity WHERE id=?',(rejected_execution,)).fetchone()
            return saved and saved[0]=='error'
        until(failed_execution,20)
        assert owner.working.admissions==2
        def all_executions_settled():
            with sqlite3.connect(db) as con:
                rows=con.execute('SELECT id,status FROM execution_entity WHERE CAST(id AS INTEGER)>?',(baseline,)).fetchall()
            return rows if rows and all(status not in {'running','waiting','new'} for _,status in rows) else None
        settled=until(all_executions_settled,20)
        assert all(status==('error' if str(execution)==str(rejected_execution) else 'success') for execution,status in settled)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
