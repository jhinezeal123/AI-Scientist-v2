"""T3 model metadata discovery uses each configured agent, never an inference turn."""
import importlib
import json
import sys

import pytest

from tests.workbench.test_agent_team_api import client, repository, P

PREFIX = '/api/agent-management'


@pytest.mark.parametrize('kind', ['native_codex', 'acp'])
def test_catalog_protocol_pagination_profile_and_cleanup(client, monkeypatch, tmp_path, kind):
    browser, gateway = client
    discovery = importlib.import_module(P+'.harness_models')
    log = tmp_path/'calls.jsonl'
    script = tmp_path/'fixture_agent.py'
    script.write_text('''import sys,json,os
for line in sys.stdin:
    msg=json.loads(line)
    with open(sys.argv[1],'a') as log:
        log.write(json.dumps({'method':msg.get('method'),'params':msg.get('params'),
          'profile':os.environ.get('CODEX_HOME'),'slack':os.environ.get('AI_SCIENTIST_SLACK_TOKEN')})+'\\n')
    if 'id' not in msg: continue
    method=msg['method']
    if method=='initialize': result={'protocolVersion':1,'agentCapabilities':{},'userAgent':'fixture/0.160.1'}
    elif method=='account/read': result={'requiresOpenaiAuth':True,'account':{'type':'chatgpt'}}
    elif method=='model/list':
        page=bool(msg['params'].get('cursor'))
        result={'data':[{'model':'second' if page else 'first','displayName':'Second' if page else 'First',
          'isDefault':not page,'defaultReasoningEffort':'high','supportedReasoningEfforts':[{'reasoningEffort':'high'}]}],
          'nextCursor':None if page else 'page-two'}
    elif method=='session/new': result={'sessionId':'fixture','configOptions':[{'category':'model','currentValue':'first',
      'options':[{'group':'Models','options':[{'value':'first','name':'First'},{'value':'second','name':'Second'}]}]}]}
    else: raise AssertionError('Unexpected inference or permission call: '+method)
    # Codex omits jsonrpc; ACP requires it.
    reply={'id':msg['id'],'result':result}
    if sys.argv[2]=='acp': reply['jsonrpc']='2.0'
    print(json.dumps(reply),flush=True)
''', encoding='utf-8')
    base = discovery.CodexCatalogChannel if kind == 'native_codex' else discovery.RpcChannel
    channels = []
    class FixtureChannel(base):
        def __init__(self, argv, cwd, *args):
            super().__init__([sys.executable,str(script),str(log),'acp' if kind=='acp' else 'codex'],cwd,*args)
            channels.append(self)
    monkeypatch.setattr(discovery,'CodexCatalogChannel' if kind=='native_codex' else 'RpcChannel',FixtureChannel)
    monkeypatch.setenv('AI_SCIENTIST_SLACK_TOKEN','unrelated-fixture-secret')
    spec = {'id':'catalog-draft','kind':kind,'executable':sys.executable,
            'config_directory':str(tmp_path/'profile') if kind=='native_codex' else '',
            'custom_models':[{'slug':'custom','name':'Custom model'}]}
    response = browser.post(PREFIX+'/harnesses/catalog-draft/models',json=spec)
    assert response.status_code == 200, response.text
    catalog = response.json()
    assert catalog['source']=='agent' and catalog['status']=='ready'
    assert [m['slug'] for m in catalog['models']]==['first','second','custom']
    assert catalog['models'][0]['isDefault'] and catalog['models'][-1]['isCustom']
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert all(row['slack'] is None for row in calls)
    if kind=='native_codex':
        assert all(row['profile']==str(tmp_path/'profile') for row in calls)
        assert [row['params'] for row in calls if row['method']=='model/list']==[{}, {'cursor':'page-two'}]
        assert catalog['version']=='0.160.1'
        assert catalog['models'][0]['capabilities']['optionDescriptors'][0]['options'][0]['isDefault']
    else:
        assert [row['method'] for row in calls]==['initialize','session/new']
    assert all(channel.receipt['process_exited'] for channel in channels)
    assert not any(h.id=='catalog-draft' for h in gateway.control_store.harnesses())


def test_catalog_failure_redacts_protocol_output_and_keeps_custom_models(client, monkeypatch):
    browser, _ = client
    discovery = importlib.import_module(P+'.harness_models')
    def fail(*args):
        raise ValueError('credential-bearing-protocol-fixture')
    monkeypatch.setattr(discovery.HarnessModels,'codex',fail)
    result = browser.post(PREFIX+'/harnesses/draft/models',json={'id':'draft','kind':'native_codex',
        'custom_models':[{'slug':'private-model','name':'Named custom model'}]})
    assert result.status_code == 200 and result.json()['status']=='error'
    assert 'credential-bearing-protocol-fixture' not in result.text
    assert result.json()['models'][0]['slug']=='private-model'


def test_t3_custom_model_metadata_and_explicit_environment_visibility_persist(client):
    browser, gateway = client
    custom = {'slug':'custom','name':'Readable name','capabilities':{'optionDescriptors':[
        {'id':'reasoningEffort','label':'Reasoning','type':'select','options':[{'id':'high','label':'High','isDefault':True}]}]}}
    spec={'id':'named','kind':'native_codex','config_directory':'~/fixture-profile','accent_color':'#68a7ff',
          'environment':{'API_KEY':'private-fixture','BASE_URL':'https://fixture.invalid'},
          'environment_sensitive':['API_KEY'],'custom_models':[custom]}
    result=browser.put(PREFIX+'/harnesses/named',json=spec)
    assert result.status_code==200,result.text
    saved=result.json()
    assert saved['environment']=={'API_KEY':'__WORKBENCH_STORED_SECRET__','BASE_URL':'https://fixture.invalid'}
    assert 'private-fixture' not in result.text
    assert saved['custom_models'][0]['capabilities']['optionDescriptors'][0]['options'][0]['isDefault']
    assert browser.put(PREFIX+'/harnesses/named',json={**saved,'name':'Renamed'}).status_code==200
    stored=next(row for row in gateway.control_store.harnesses() if row.id=='named')
    assert stored.environment['API_KEY']=='private-fixture' and stored.config_directory=='~/fixture-profile'
    pair={'id':'named-pair','name':'Pair','harness':'named','model':'custom'}
    assert browser.put(PREFIX+'/agent-presets/named-pair',json=pair).status_code==200
    assert browser.put(PREFIX+'/harnesses/named',json={**saved,'archived':True}).status_code==409
    assert browser.delete(PREFIX+'/agent-presets/named-pair').status_code==200
    assert browser.put(PREFIX+'/harnesses/named',json={**saved,'archived':True}).status_code==200
    assert all(row['spec']['id']!='named' for row in browser.get(PREFIX+'/harnesses?probe=false').json())
    assert browser.put(PREFIX+'/agent-presets/named-pair',json=pair).status_code==409
