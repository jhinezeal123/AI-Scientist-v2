"""Failure cases observed during PR #3 review; no paid providers or Kaggle."""
import importlib
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Timer
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_scientist.workbench.runtime import _agent_gateway_class
from ai_scientist.workbench.agents.contracts import RuntimeRequest, RuntimeCancelled

Gateway = _agent_gateway_class()
acp = importlib.import_module(Gateway.__module__.rsplit('.', 1)[0] + '.acp')
http_api = importlib.import_module(Gateway.__module__.rsplit('.', 1)[0] + '.http_api')


@pytest.fixture
def team(tmp_path):
    profile = tmp_path / 'profile.json'
    profile.write_text(json.dumps({'seats': {'lead': {'provider': 'codex'},
        'builder': {'provider': 'codex'}}, 'default_seat': 'lead'}))
    gateway = Gateway(SimpleNamespace(), tmp_path, spec_path=profile)
    gateway.create_rig('team', seats=['lead'])
    return gateway


def expire(team, task_id):
    con = sqlite3.connect(team.store.path)
    try:
        con.execute("UPDATE tasks SET lease_until='2000-01-01T00:00:00+00:00' WHERE id=?", (task_id,))
        con.commit()
    finally:
        con.close()


def test_concurrent_claims_do_not_double_lease_one_seat(team):
    for i in range(3):
        team.enqueue('team', 'lead', str(i), {'task': i})
    second = Gateway(SimpleNamespace(), team.workspace_root, spec_path=team.spec_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda gateway: gateway.claim('team', 'lead'), [team, second]))
    assert sum(claim is not None for claim in claims) == 1
    assert team.claim('team', 'lead') is None


def test_expired_owner_cannot_complete_or_unlock_dependency(team):
    first = team.enqueue('team', 'lead', 'first', {'task': 'one'})
    team.enqueue('team', 'lead', 'second', {'task': 'two'}, depends_on=first['id'])
    lease = team.claim('team', 'lead')
    expire(team, first['id'])
    with pytest.raises(ValueError, match='expired'):
        team.finish(first['id'], lease['lease_token'], result={'done': True})
    assert [task['state'] for task in team.snapshot('team')['tasks']] == ['UNKNOWN', 'PENDING']
    assert team.claim('team', 'lead') is None


def test_unknown_owner_blocks_independent_task_after_restart(team):
    task = team.enqueue('team', 'lead', 'first', {'task': 'one'})
    team.enqueue('team', 'lead', 'second', {'task': 'independent'})
    team.claim('team', 'lead')
    expire(team, task['id'])
    restarted = Gateway(SimpleNamespace(), team.workspace_root, spec_path=team.spec_path)
    assert restarted.claim('team', 'lead') is None
    assert restarted.snapshot('team')['tasks'][0]['state'] == 'UNKNOWN'


def test_distinct_seats_can_claim_in_parallel(team):
    team.create_rig('pair', seats=['lead', 'builder'])
    for seat in ['lead', 'builder']:
        team.enqueue('pair', seat, seat, {'task': seat})
    assert team.claim('pair', 'lead')['state'] == 'LEASED'
    assert team.claim('pair', 'builder')['state'] == 'LEASED'


def test_control_api_enforces_persisted_rig_membership(team, monkeypatch):
    app = FastAPI()
    app.include_router(http_api.create_router())
    app.state.runtime = SimpleNamespace(runtime=team)
    monkeypatch.setenv('AI_SCIENTIST_AGENT_CONTROL_TOKEN', 'fixture-review')
    headers = {'Authorization': 'Bearer fixture-review'}
    with TestClient(app) as client:
        assert client.post('/api/agent-management/rigs/team/tasks', headers=headers,
            json={'seat': 'builder', 'request_id': 'outside', 'task': {}}).status_code == 409
        for sender, recipient in [('builder', '*'), ('lead', 'builder')]:
            assert client.post('/api/agent-management/rigs/team/messages', headers=headers,
                json={'sender': sender, 'recipient': recipient, 'body': 'private'}).status_code == 409
        client.post('/api/agent-management/rigs/team/messages', headers=headers,
            json={'sender': 'lead', 'recipient': '*', 'body': 'team-only'})
        assert client.get('/api/agent-management/rigs/team/seats/builder/inbox', headers=headers).status_code == 404
        assert client.get('/api/agent-management/rigs/missing/seats/lead/inbox', headers=headers).status_code == 404
    with pytest.raises(ValueError, match='rig'):
        team.claim('team', 'builder')


@pytest.fixture
def fixture_agent(tmp_path, monkeypatch):
    processes = []
    original = acp.subprocess.Popen
    def observe(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(acp.subprocess, 'Popen', observe)
    def create(*, auth_required=False, stalled=False, text='fixture'):
        script = tmp_path / ('agent-' + str(len(list(tmp_path.glob('agent-*')))) + '.py')
        settings = json.dumps({'auth_required': auth_required, 'stalled': stalled, 'text': text})
        script.write_text('import json,sys,time\nsettings=json.loads(' + repr(settings) + ')\n' + '''
for line in sys.stdin:
 m=json.loads(line)
 if m['method']=='initialize':
  result={'protocolVersion':1,'agentCapabilities':{},'authMethods':[{'id':'login','name':'Login'}]}
 elif m['method']=='session/new':
  if settings['auth_required']:
   print(json.dumps({'jsonrpc':'2.0','id':m['id'],'error':{'code':-32000,'message':'private details'}}),flush=True)
   continue
  result={'sessionId':'fixture-session'}
 elif m['method']=='session/prompt':
  print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':'fixture-session','update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':settings['text']}}}}),flush=True)
  result={'stopReason':'end_turn'}
 else: result={}
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
 if m['method']=='session/new' and settings['stalled']:
  time.sleep(3)
  break
''', encoding='utf-8')
        return acp.AcpStdioRuntime(sys.executable, ('-u', str(script)))
    yield create
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)


def test_advertised_auth_methods_do_not_reject_logged_in_agent(tmp_path, fixture_agent):
    result = fixture_agent().run(RuntimeRequest('auth', 'mvp0_report', 'prompt', tmp_path, timeout_seconds=5),
        lambda event: None, lambda: False)
    assert result.text == 'fixture' and result.session_id == 'fixture-session'


def test_actual_auth_required_is_reported_without_agent_error_details(tmp_path, fixture_agent):
    with pytest.raises(RuntimeError, match='sign in separately') as error:
        fixture_agent(auth_required=True).run(RuntimeRequest('auth', 'mvp0_report', 'prompt', tmp_path, timeout_seconds=5),
            lambda event: None, lambda: False)
    assert 'private details' not in str(error.value)


@pytest.mark.parametrize('cancel', [False, True])
def test_stalled_stdin_obeys_deadline_and_cancellation(tmp_path, fixture_agent, cancel):
    cancellation = Event()
    timer = Timer(.5, cancellation.set) if cancel else None
    if timer:
        timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(RuntimeCancelled if cancel else TimeoutError):
            fixture_agent(stalled=True).run(RuntimeRequest('stall', 'mvp0_report', 'x' * 1_000_000,
                tmp_path, timeout_seconds=5 if cancel else 1), lambda event: None, cancellation.is_set)
        assert time.monotonic() - started < 2.5
    finally:
        if timer:
            timer.cancel()


def test_acp_output_limit_counts_utf8_bytes(tmp_path, fixture_agent):
    with pytest.raises(ValueError, match='size limit'):
        fixture_agent(text='ế' * 100).run(RuntimeRequest('bytes', 'mvp0_report', 'prompt', tmp_path,
            timeout_seconds=5, max_output_bytes=200), lambda event: None, lambda: False)
