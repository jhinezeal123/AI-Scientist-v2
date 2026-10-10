import importlib
import json
import time
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from tests.workbench.test_agent_team_execution import repository, FixtureRegistry, Platform, AgentStore, models, wait_finished

PACKAGE = Platform.__module__.rsplit('.', 1)[0]


def test_completion_survives_failed_chat_notification(repository, monkeypatch):
    fixture = repository / 'fixture.py'
    fixture.write_text("import json,sys; json.load(sys.stdin); print(json.dumps({'summary':'ok','files':[],'checks':[],'handoff':''}))")
    control = Platform(AgentStore(repository / '.workbench/control.sqlite'), repository, registry=FixtureRegistry(fixture))
    control.create('team', models.RigSpec(name='Team', seats=[models.AgentSpec(id='lead')]))
    monkeypatch.setattr(control.store.queue, 'send', lambda *args: (_ for _ in ()).throw(ValueError('chat unavailable')))
    control.enqueue('team', 'lead', 'first', models.TaskRequest(instruction='First'))
    control.start('team')
    first = wait_finished(control, 'team', 1)
    control.enqueue('team', 'lead', 'second', models.TaskRequest(instruction='Second'))
    finished = wait_finished(control, 'team', 2)
    control.close()
    assert all(t['state'] == 'DONE' for t in finished['tasks'])
    assert all(s['state'] == 'DONE' for s in finished['sessions'])
    assert all(s['state'] == 'IDLE' for s in finished['seats'])


def test_unknown_seat_fences_pending_task_without_unknown_task(repository):
    control = Platform(AgentStore(repository / '.workbench/control.sqlite'), repository)
    control.create('team', models.RigSpec(name='Team', seats=[models.AgentSpec(id='lead')]))
    control.enqueue('team', 'lead', 'pending', models.TaskRequest(instruction='Wait'))
    with control.store.connect(True) as con:
        con.execute("UPDATE seats SET state='UNKNOWN' WHERE rig_id='team'")
    control.store.enabled('team', True)
    control.tick()
    assert control.store.snapshot('team')['tasks'][0]['state'] == 'PENDING'
    assert not control.active
    control.close()


def test_queue_capacity_is_atomic_and_duplicate_bypasses_capacity(repository):
    queue = AgentStore(repository / '.workbench/control.sqlite')
    queue.create_rig('team', {'seats': [{'id': 'lead'}]})
    def enqueue(i):
        try:
            return queue.enqueue('team', 'lead', str(i), {'instruction': 'same'}, max_pending=8)
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=12) as pool:
        accepted = [row for row in pool.map(enqueue, range(30)) if row]
    assert len(accepted) == 8
    first = accepted[0]
    assert queue.enqueue('team', 'lead', first['request_id'], {'instruction': 'same'}, max_pending=8)['id'] == first['id']
    with pytest.raises(ValueError, match='full'):
        queue.enqueue('team', 'lead', 'overflow', {}, max_pending=8)


def test_shrink_grow_and_enabled_topology_guard(repository):
    control = Platform(AgentStore(repository / '.workbench/control.sqlite'), repository)
    spec = models.RigSpec(name='Team', seats=[models.AgentSpec(id='lead'), models.AgentSpec(id='builder')])
    control.create('team', spec)
    control.store.enabled('team', True)
    with pytest.raises(ValueError, match='Pause'):
        control.store.update_spec('team', spec, 1)
    control.store.enabled('team', False)
    control.store.update_spec('team', spec.model_copy(update={'seats': spec.seats[:1]}), 1)
    control.store.update_spec('team', spec, 2)
    assert next(s for s in control.store.snapshot('team')['seats'] if s['id'] == 'builder')['state'] == 'IDLE'
    control.close()


def test_telemetry_unknown_fields_remain_null(monkeypatch):
    resources = importlib.import_module(PACKAGE + '.resources')
    monkeypatch.setattr(resources, 'resource_limits', lambda *_: [])
    team = {'sessions': [{'provider_id': 'codex', 'usage': {'input_tokens': 12}}, {'provider_id': 'codex', 'usage': {}}],
            'tasks': [], 'seats': [], 'spec': {'max_parallel': 2, 'pods': []}}
    control = SimpleNamespace(store=SimpleNamespace(snapshot=lambda _: team))
    usage = resources.telemetry(control, 'team')['providers']['codex']
    assert usage['input_tokens'] == 12 and usage['output_tokens'] is None and usage['cost_usd'] is None


def test_client_never_follows_redirect_with_credentials():
    interfaces = importlib.import_module(PACKAGE + '.interfaces')
    from urllib.request import Request
    with pytest.raises(ValueError, match='redirects'):
        interfaces.NoRedirect().redirect_request(Request('https://private.example'), None, 302, 'Moved', {}, 'https://other.example')


def test_resource_pool_serializes_selected_seats_and_preserves_other_capacity(repository):
    resources = importlib.import_module(PACKAGE + '.resources')
    fixture = repository / 'fixture.py'
    fixture.write_text("import json,sys,time; json.load(sys.stdin); time.sleep(.5); print(json.dumps({'summary':'ok','files':[],'checks':[],'handoff':''}))")
    control = Platform(AgentStore(repository / '.workbench/control.sqlite'), repository, registry=FixtureRegistry(fixture))
    control.create('team', models.RigSpec(name='Pool',seats=[models.AgentSpec(id='a'),models.AgentSpec(id='b'),models.AgentSpec(id='c')]))
    resources.configure_resource(control.store,'team',resources.CodingResource(id='cpu',name='CPU pool',seat_ids=['a','b'],max_parallel=1))
    for seat in ('a','b','c'):
        control.enqueue('team',seat,seat,models.TaskRequest(instruction='Wait briefly'))
    control.store.enabled('team',True)
    control.tick()
    with control.lock:
        active={key[1] for key in control.active}
    assert active=={'a','c'}
    with pytest.raises(ValueError,match='Pause'):
        resources.remove_resource(control.store,'team','cpu')
    control.start('team')
    finished=wait_finished(control,'team',3)
    control.close()
    assert all(t['state']=='DONE' for t in finished['tasks'])


def test_failed_retry_requires_paused_team_and_verified_stop(repository):
    control=Platform(AgentStore(repository/'.workbench/control.sqlite'),repository)
    control.create('team',models.RigSpec(name='Team',seats=[models.AgentSpec(id='lead')]))
    task=control.enqueue('team','lead','failed',models.TaskRequest(instruction='Original immutable input'))
    claimed=control.store.queue.claim('team','lead')
    session=control.store.begin_session(claimed,'codex')
    control.store.fail_task(task['id'],claimed['lease_token'],error='Known failure')
    control.store.complete_session(session,state='FAILED',receipt={})
    with pytest.raises(ValueError,match='receipt'):
        control.store.retry_stopped('team',task['id'])
    control.store.complete_session(session,state='FAILED',receipt={'process_exited':True,'tree_stopped':True})
    control.store.enabled('team',True)
    with pytest.raises(ValueError,match='Pause'):
        control.store.retry_stopped('team',task['id'])
    control.store.enabled('team',False)
    assert control.store.retry_stopped('team',task['id'])['state']=='PENDING'
    replay=control.enqueue('team','lead','failed',models.TaskRequest(instruction='Original immutable input'))
    assert replay['id']==task['id']
    control.close()


@pytest.mark.skipif(os.name!='nt',reason='Installed Windows sandbox ACL regression')
def test_real_windows_cli_isolation_and_cross_seat_acl_recovery(repository):
    from ai_scientist.workbench.codex_executable import resolve_codex_executable
    try:
        executable=resolve_codex_executable('codex')
    except (FileNotFoundError,ValueError):
        pytest.skip('Native Codex OS sandbox is not installed')
    control=Platform(AgentStore(repository/'.workbench/control.sqlite'),repository,codex=SimpleNamespace(executable=str(executable)))
    secret=repository/'.workbench/projects/secret.txt';secret.parent.mkdir(parents=True);secret.write_text('synthetic-canary')
    paths={seat:control.workspaces.ensure('scope',seat,'HEAD')[0] for seat in ('a','b')}
    fixture=repository/'cli-fixture.py'
    fixture.write_text("""import json,pathlib,sys
json.load(sys.stdin)
own=pathlib.Path('src/demo.py').read_text()
denied=[]
for name in sys.argv[1:]:
 try:pathlib.Path(name).read_text();denied.append(False)
 except OSError:denied.append(True)
print(json.dumps({'summary':json.dumps({'own':own,'denied':denied}),'files':[],'checks':[],'handoff':''}))
""")
    for seat,other in [('a','b'),('b','a'),('a','b')]:
        spec=models.HarnessSpec(id='fixture',kind='cli_json',executable=sys.executable,args=[str(fixture),str(secret),str(paths[other]/'src/demo.py')])
        control.store.put_harness(spec)
        adapter=control.registry.resolve('fixture')
        handle=adapter.start(models.AgentSpec(id=seat,harness='fixture'),paths[seat])
        result=adapter.send(handle,'No model call',request_id='scope-'+seat,timeout=30,emit=lambda _:None,started=lambda _:None)
        summary=json.loads(result.result.summary)
        assert summary=={'own':'original\n','denied':[True,True]}
        assert result.receipt['tree_stopped']
    control.close()
