import importlib
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from ai_scientist.workbench.runtime import _agent_gateway_class
from tests.workbench.test_agent_team_execution import repository

Gateway = _agent_gateway_class()
P = Gateway.__module__.rsplit('.',1)[0]
api = importlib.import_module(P+'.team_api')
models = importlib.import_module(P+'.models')
remote = importlib.import_module(P+'.remote')


@pytest.fixture
def client(repository, monkeypatch):
    monkeypatch.setenv('AI_SCIENTIST_AGENT_CONTROL_TOKEN','fixture-only-key')
    gateway=Gateway(SimpleNamespace(executable='',model=None),repository)
    app=FastAPI()
    app.state.runtime=SimpleNamespace(runtime=gateway)
    app.include_router(api.create_team_router())
    app.middleware('http')(api.remote_boundary)
    with TestClient(app,headers={'Authorization':'Bearer fixture-only-key'}) as client:
        yield client,gateway
    gateway.close()


def create(client, identifier='team'):
    spec=models.templates()[1]
    response=client.post('/api/agent-management/teams',json={'id':identifier,'spec':spec})
    assert response.status_code==200,response.text
    return response.json()


def test_gui_journey_and_workflow_idempotency(client):
    client,gateway=client
    team=create(client)
    base='/api/agent-management/teams/team'
    response=client.post(base+'/workflow',json={'request_id':'workflow','instruction':'Inspect and improve demo'})
    assert response.status_code==200,response.text
    rows=response.json()
    assert [t['seat'] for t in rows]==['lead','builder','qa','reviewer']
    assert rows[1]['depends_on']==rows[0]['id']
    assert client.post(base+'/workflow',json={'request_id':'workflow','instruction':'Inspect and improve demo'}).json()==rows
    assert client.post(base+'/workflow',json={'request_id':'workflow','instruction':'Changed'}).status_code==409
    assert len(client.get(base).json()['tasks'])==4
    for row in rows:
        assert client.delete(base+'/tasks/'+row['id']).status_code==200
    assert client.get(base+'/seats/builder/files').status_code==200
    file=client.get(base+'/seats/builder/file',params={'path':'src/demo.py'}).json()
    file['content']='changed\n'
    assert client.put(base+'/seats/builder/file',json=file).status_code==200
    assert client.put(base+'/seats/builder/file',json=file).status_code==409
    assert 'changed' in client.get(base+'/seats/builder/review').json()['diff']
    assert client.get(base+'/seats/builder/file',params={'path':'../profiles/credentials.json'}).status_code==409
    assert client.post(base+'/snapshots').status_code==200


def test_pair_scope_csrf_revocation_and_one_time_code(client):
    client,gateway=client
    create(client)
    create(client,'other')
    pairing=client.post('/api/agent-management/pair',json={'scopes':['read','message'],'rig_ids':['team']}).json()
    client.headers.pop('Authorization')
    body={'pairing_id':pairing['pairing_id'],'code':pairing['code'],'name':'Phone'}
    response=client.post('/api/agent-management/pair/exchange',json=body)
    assert response.status_code==200,response.text
    result=response.json()
    assert client.get('/api/agent-management/identity').json()['csrf']==result['csrf']
    assert 'token' not in result and 'HttpOnly' in response.headers['set-cookie']
    assert client.post('/api/agent-management/pair/exchange',json=body).status_code==409
    assert client.get('/api/agent-management/teams/team').status_code==200
    assert client.get('/api/agent-management/teams/other').status_code==403
    assert len(client.get('/api/agent-management/teams').json())==1
    data={'sender':'lead','recipient':'*','body':'hello'}
    assert client.post('/api/agent-management/teams/team/messages',json=data).status_code==403
    client.headers['X-Agent-CSRF']=result['csrf']
    assert client.post('/api/agent-management/teams/team/messages',json=data).status_code==200
    assert client.post('/api/agent-management/teams/team/start').status_code==403
    client.headers['Authorization']='Bearer fixture-only-key'
    assert client.delete('/api/agent-management/devices/'+result['device_id']).status_code==200
    client.headers.pop('Authorization')
    assert client.get('/api/agent-management/teams/team').status_code==401
    with gateway.platform.store.connect() as con:
        rows=[dict(r) for r in con.execute('SELECT * FROM devices')]
    assert client.cookies.get(remote.COOKIE) not in json.dumps(rows)


def test_https_reverse_proxy_does_not_expose_bootstrap_or_legacy_api(client,monkeypatch):
    local,gateway=client
    create(local)
    monkeypatch.setenv('AI_SCIENTIST_AGENT_PUBLIC_ORIGIN','https://private.example')
    with TestClient(local.app,base_url='https://private.example',headers={'Authorization':'Bearer fixture-only-key'}) as device:
        assert device.get('/api/agent-management/teams').status_code==403
        assert device.get('/api/projects').status_code==403
        pairing=remote.DeviceAccess(gateway.platform.store).pairing(scopes=['read'],rig_ids=['team'])
        response=device.post('/api/agent-management/pair/exchange',json={**{k:pairing[k] for k in ('pairing_id','code')},'name':'Remote browser'})
        assert response.status_code==200
        assert 'Secure' in response.headers['set-cookie']
        device.headers.pop('Authorization')
        assert device.get('/api/agent-management/teams/team').status_code==200
        assert device.get('/api/agent-management/harnesses?details=true').status_code==403
        public=device.get('/api/agent-management/harnesses').json()
        assert all('executable' not in h['spec'] and 'args' not in h['spec'] for h in public)
        assert device.get('/api/agent-management/teams',headers={'Origin':'https://evil.example'}).status_code==403
        assert device.get('/api/projects').status_code==403


def test_agent_cannot_approve_or_impersonate(client):
    client,gateway=client
    create(client)
    token=remote.DeviceAccess(gateway.platform.store).agent_token('team','builder')['token']
    client.headers['Authorization']='Bearer '+token
    assert client.post('/api/agent-management/teams/team/start').status_code==403
    assert client.post('/api/agent-management/pair',json={'scopes':['admin'],'rig_ids':['*']}).status_code==403
    assert client.post('/api/agent-management/teams/team/messages',json={'sender':'lead','recipient':'*','body':'fake'}).status_code==403
    assert client.post('/api/agent-management/teams/team/tasks',json={'seat':'lead','request_id':'bad','task':{'instruction':'fake'}}).status_code==403


def test_agent_read_scope_covers_diff_snapshot_and_event_content(client):
    client,gateway=client
    create(client)
    control=gateway.platform
    path,_=control.workspaces.ensure('team','builder','HEAD')
    (path/'src/demo.py').write_text('visible source\n')
    (path/'private.txt').write_text('hidden source\n')
    task=control.enqueue('team','lead','private-task',models.TaskRequest(instruction='private payload'))
    with control.store.connect(True) as con:
        con.execute("UPDATE tasks SET result_json=? WHERE id=?",(json.dumps({'files':[{'path':'private.txt','content':'peer canary'}],'output':'peer terminal canary','summary':'shared summary'}),task['id']))
    # The SQL scope filter must run before LIMIT; peer event traffic cannot starve
    # the receiving seat's cursor.
    for _ in range(205):
        control.store.publish('output',{'text':'peer event canary'},rig_id='team',seat_id='lead')
    control.store.publish('output',{'text':'own event'},rig_id='team',seat_id='builder')
    token=remote.DeviceAccess(control.store).agent_token('team','builder')['token']
    client.headers['Authorization']='Bearer '+token
    base='/api/agent-management/teams/team'
    assert client.get(base+'/seats/lead/review').status_code==403
    diff=client.get(base+'/seats/builder/review').json()['diff']
    assert 'visible source' in diff and 'hidden source' not in diff
    snapshot=client.get(base).text
    assert 'shared summary' in snapshot and 'peer canary' not in snapshot and 'private payload' not in snapshot and 'peer terminal canary' not in snapshot
    events=client.get(base+'/events').text
    assert 'own event' in events and 'peer event canary' not in events


def test_transport_origin_and_rebinding(client):
    client,_=client
    assert client.get('/api/agent-management/identity',headers={'Origin':'https://evil.test'}).status_code==403
    assert client.get('/api/agent-management/identity',headers={'Host':'evil.test','Origin':'http://evil.test'}).status_code==403
