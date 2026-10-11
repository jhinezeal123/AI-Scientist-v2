"""Provider setup from the UI: durable instances, custom models, masked values."""
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from tests.workbench.test_agent_team_api import client, repository, P

PREFIX = '/api/agent-management'


def test_multiple_provider_instances_and_custom_models_persist(client):
    browser, gateway = client
    for index in range(5):
        spec = {'id':f'custom-{index}', 'name':f'Agent {index}', 'kind':'native_codex',
                'executable':sys.executable, 'models':['suggested-model']}
        response = browser.put(PREFIX+'/harnesses/'+spec['id'], json=spec)
        assert response.status_code == 200, response.text
        preset = {'id':f'pair-{index}', 'name':f'Preset {index}', 'harness':spec['id'], 'model':'new-model-outside-suggestions'}
        assert browser.put(PREFIX+'/agent-presets/'+preset['id'], json=preset).status_code == 200
    specs = browser.get(PREFIX+'/harnesses?probe=false&details=true').json()
    assert all(row['probe'] is None for row in specs)
    assert len([row for row in specs if row['spec']['id'].startswith('custom-')]) == 5
    assert browser.get(PREFIX+'/agent-presets').json()[-1]['model'] == 'new-model-outside-suggestions'
    presets = importlib.import_module(P+'.presets').Presets(gateway.control_store)
    assert presets.list()[-1]['harness'] == 'custom-4'
    harnesses = importlib.import_module(P+'.harnesses')
    model = importlib.import_module(P+'.models')
    adapter = harnesses.NativeHarness(model.HarnessSpec.model_validate(spec))
    seat = model.AgentSpec(id='seat',harness='custom-4',model='new-model-outside-suggestions')
    assert adapter.start(seat,Path('.')).seat.model == seat.model


def test_provider_environment_is_masked_preserved_replaced_and_removed(client):
    browser, gateway = client
    spec = {'id':'private','name':'Private provider','kind':'native_codex',
            'environment':{'OPENAI_API_KEY':'fixture-secret','OPENAI_BASE_URL':'https://fixture.invalid'}}
    response = browser.put(PREFIX+'/harnesses/private',json=spec)
    assert response.status_code == 200,response.text
    masked = response.json()
    assert 'fixture-secret' not in response.text
    assert set(masked['environment'].values()) == {'__WORKBENCH_STORED_SECRET__'}
    assert 'environment' not in next(r['spec'] for r in browser.get(PREFIX+'/harnesses?probe=false').json() if r['spec']['id']=='private')
    assert 'fixture-secret' not in browser.get(PREFIX+'/harnesses?probe=false&details=true').text
    assert browser.put(PREFIX+'/harnesses/private',json={**masked,'name':'Renamed'}).status_code == 200
    stored = next(h for h in gateway.control_store.harnesses() if h.id=='private')
    assert stored.environment['OPENAI_API_KEY'] == 'fixture-secret'
    updated = {**masked,'environment':{'OPENAI_API_KEY':'replacement'}}
    assert browser.put(PREFIX+'/harnesses/private',json=updated).status_code == 200
    stored = next(h for h in gateway.control_store.harnesses() if h.id=='private')
    assert stored.environment == {'OPENAI_API_KEY':'replacement'}
    assert browser.put(PREFIX+'/harnesses/private',json={**masked,'environment':{}}).status_code == 200
    assert next(h for h in gateway.control_store.harnesses() if h.id=='private').environment == {}


def test_fast_catalog_does_not_execute_any_provider_and_check_does_not_save(client, monkeypatch):
    browser, gateway = client
    native = importlib.import_module(P+'.harnesses').NativeHarness
    calls=[]
    def probe(self):
        calls.append(self.spec.id)
        return {'ready':True,'version':'untrusted output fixture-secret','capabilities':{}}
    monkeypatch.setattr(native,'probe',probe)
    browser.get(PREFIX+'/agent-presets')
    assert browser.get(PREFIX+'/harnesses?probe=false&details=true').status_code==200
    assert calls==[]
    body={'id':'draft','kind':'native_codex','environment':{'OPENAI_API_KEY':'fixture-secret'}}
    result=browser.post(PREFIX+'/harnesses/draft/probe',json=body)
    assert result.status_code==200 and result.json()['ready']
    assert 'fixture-secret' not in result.text
    assert calls==['draft']
    assert not any(h.id=='draft' for h in gateway.control_store.harnesses())


@pytest.mark.parametrize('key',['PATH','PYTHONPATH','NODE_OPTIONS','AI_SCIENTIST_AGENT_CONTROL_TOKEN','LD_PRELOAD'])
def test_provider_config_rejects_process_or_control_environment_overrides(client,key):
    browser,_ = client
    response=browser.put(PREFIX+'/harnesses/unsafe',json={'id':'unsafe','kind':'native_codex','environment':{key:'fixture-secret'}})
    assert response.status_code==422
    assert 'fixture-secret' not in response.text


def test_native_process_receives_only_explicit_provider_environment(client,monkeypatch,tmp_path):
    _,gateway=client
    native=importlib.import_module(P+'.harnesses')
    model=importlib.import_module(P+'.models')
    monkeypatch.setenv('AI_SCIENTIST_SLACK_TOKEN','unrelated-secret')
    adapter=native.NativeHarness(model.HarnessSpec(id='test',kind='cli_json',executable=sys.executable,environment={'OPENAI_API_KEY':'explicit-key'}))
    captured={}
    def run(argv,cwd,body,**kwargs):
        captured.update(kwargs['env'])
        return b'{"summary":"done","files":[],"checks":[],"handoff":""}',{}
    monkeypatch.setattr(native,'run_process',run)
    handle=adapter.start(model.AgentSpec(id='seat'),tmp_path)
    adapter.send(handle,'fixture',request_id='test',timeout=2,emit=lambda _:None,started=lambda _:None)
    assert captured['OPENAI_API_KEY']=='explicit-key'
    assert 'AI_SCIENTIST_SLACK_TOKEN' not in captured


def test_cached_models_are_suggestions_not_an_allowlist(client,monkeypatch,tmp_path):
    browser,_ = client
    (tmp_path/'models_cache.json').write_text('{"models":[{"slug":"cached-model"},{"slug":"cached-model"},{"slug":"internal-model","visibility":"hide"}]}')
    monkeypatch.setenv('CODEX_HOME',str(tmp_path))
    specs=browser.get(PREFIX+'/harnesses?probe=false').json()
    codex=next(h['spec'] for h in specs if h['spec']['id']=='codex')
    assert codex['models'].count('cached-model')==1
    assert 'internal-model' not in codex['models']
    assert browser.put(PREFIX+'/agent-presets/custom',json={'id':'custom','name':'Custom','harness':'codex','model':'not-cached'}).status_code==200
