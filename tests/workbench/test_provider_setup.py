"""Provider setup owns installations/auth; probes never execute research turns."""
import importlib
import io
import json
from pathlib import Path
import sys
import time
import zipfile

import pytest

from tests.workbench.test_agent_team_api import client, repository, P

PREFIX='/api/agent-management'
catalog_module=importlib.import_module(P+'.providers.catalog')
install_module=importlib.import_module(P+'.providers.installations')
operations=importlib.import_module(P+'.providers.operations')
profiles_module=importlib.import_module(P+'.providers.antigravity')
models=importlib.import_module(P+'.models')


def fixture_catalog():
    bundled=Path(catalog_module.__file__).parents[1]/'vendor/t3code/acp-registry.json'
    return catalog_module.RegistryCatalog.validate(json.loads(bundled.read_text(encoding='utf-8')))


def test_full_registry_is_available_without_credentials(client,monkeypatch):
    browser,gateway=client
    monkeypatch.setattr(catalog_module.RegistryCatalog,'index',lambda self,refresh=False:fixture_catalog())
    result=browser.get(PREFIX+'/acp-registry')
    assert result.status_code==200,result.text
    agents=result.json()['agents']
    assert len(agents)>=41
    assert {'antigravity-acp','codex-acp','claude-acp','gemini','cursor','opencode','github-copilot-cli','kimi','qwen-code'} <= {a['id'] for a in agents}
    assert all(a['distribution'] in {'binary','npx','uvx',None} for a in agents)
    assert browser.get(PREFIX+'/acp-registry?query=Antigravity').json()['agents'][0]['id']=='antigravity-acp'
    assert not gateway.harness_catalog.provider_setup.installs
    assert gateway._platform is None and not gateway._project_platforms


def test_registry_refresh_does_not_silently_replace_installed_runtime(tmp_path):
    agent={'id':'fixture','version':'1.0.0','name':'Fixture','distribution':{'npx':{'package':'fixture@1.0.0','args':['--old'],'env':{'MODE':'old'}}}}
    class Index:
        def agent(self,_):return agent
        def distribution(self,row,preference='auto'):return 'npx',row['distribution']['npx']
    installations=install_module.Installations(tmp_path/'tools',Index())
    root=installations.directory(agent,'npx')
    root.mkdir(parents=True)
    entry=root/'entry.js';entry.write_text('// fixture')
    install_module.atomic_json(root/'install.json',{'agentId':'fixture','version':'1.0.0','distribution':'npx','entrypoint':'entry.js','args':['--old'],'env':{'MODE':'old'}})
    agent['version']='2.0.0';agent['distribution']['npx']={'package':'fixture@2.0.0','args':['--new']}
    spec=models.HarnessSpec(id='fixture',kind='acp',registry_agent_id='fixture')
    command,args,environment,version=installations.resolve(spec)
    assert version=='1.0.0' and args[-1]=='--old' and environment=={'MODE':'old'}
    assert installations.receipt(agent,exact=True) is None


def test_archive_traversal_is_rejected_without_touching_other_files(tmp_path,monkeypatch):
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as package:package.writestr('../outside.txt','unsafe')
    class Download(io.BytesIO):
        headers={}
    monkeypatch.setattr(install_module,'urlopen',lambda *a,**k:Download(archive.getvalue()))
    installations=install_module.Installations(tmp_path/'tools',None)
    stage=tmp_path/'tools/stage';stage.mkdir()
    with pytest.raises(operations.SetupError,match='unsafe path'):
        installations.binary({'archive':'https://example.invalid/runtime.zip','cmd':'entry.exe'},stage,operations.SetupOperation('fixture','owner'))
    assert not (tmp_path/'tools/outside.txt').exists()


def test_antigravity_profile_is_private_durable_and_has_short_temp(tmp_path):
    runtime=tmp_path/'runtime';runtime.mkdir()
    (runtime/'localharness_external.exe').touch()
    (runtime/'localharness_external').touch()
    profiles=profiles_module.AntigravityProfiles(tmp_path/'accounts',tmp_path/'short-tmp')
    first=models.HarnessSpec(id='first',kind='acp',registry_agent_id='antigravity-acp')
    second=first.model_copy(update={'id':'second'})
    token=profiles.token(first);token.parent.mkdir(exist_ok=True);token.write_text('{}')
    environment,temp=profiles.environment(first,runtime/'agy_acp_server.exe',{'GEMINI_API_KEY':'unrelated','GOOGLE_API_KEY':'unrelated'})
    assert profiles.cached(first) and not profiles.cached(second)
    assert 'GEMINI_API_KEY' not in environment and 'GOOGLE_API_KEY' not in environment
    assert temp.parent==tmp_path/'short-tmp'
    assert profiles_module.AntigravityProfiles(tmp_path/'accounts').cached(first)
    profiles.logout(first)
    assert not profiles.cached(first)


@pytest.mark.parametrize('url',[
    'https://evil.invalid/o/oauth2/v2/auth?state=s&redirect_uri=http://127.0.0.1:9999/&response_type=code',
    'https://accounts.google.com/o/oauth2/v2/auth?state=s&state=other&redirect_uri=http://127.0.0.1:9999/&response_type=code',
    'https://accounts.google.com/o/oauth2/v2/auth?state=s&redirect_uri=http://127.0.0.1:80/&response_type=code',
])
def test_google_auth_url_is_bound_to_google_and_a_loopback_callback(url):
    with pytest.raises(operations.SetupError):profiles_module.authorization_url(url)


def fake_acp(tmp_path,method):
    script=tmp_path/'peer.py'
    script.write_text('''import json,sys,os
for line in sys.stdin:
    request=json.loads(line)
    if 'method' not in request:continue
    method=request['method'];params=request.get('params',{})
    if method=='initialize':
        assert params['clientCapabilities'].get('elicitation')=={'url':{}}
        value={'protocolVersion':1,'authMethods':[METHOD],'agentCapabilities':{}}
    elif method=='authenticate':
        print(json.dumps({'jsonrpc':'2.0','id':'consent','method':'session/elicitation','params':{'mode':'url','url':'https://example.invalid/login','elicitationId':'consent'}}),flush=True)
        reply=json.loads(sys.stdin.readline());assert reply['result']['action']=='accept'
        value={}
    elif method=='session/new':
        value={'sessionId':'session','configOptions':[{'id':'model','currentValue':'account-model','options':[{'value':'account-model','name':'Account model'}]}]}
    else:raise AssertionError('unexpected inference: '+method)
    print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':value}),flush=True)
'''.replace('METHOD',repr(method)),encoding='utf-8')
    return {'id':'fixture','kind':'acp','executable':sys.executable,'args':[str(script)]}


def wait_phase(browser,phase):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        state=browser.get(PREFIX+'/harnesses/fixture/auth').json()
        if state['phase']==phase:return state
        if state['phase']=='failed':pytest.fail(state['message'])
        time.sleep(.03)
    pytest.fail('provider setup timed out')


def test_browser_signin_uses_current_flow_owner_and_verifies_models_without_prompt(client,tmp_path):
    browser,gateway=client
    spec=fake_acp(tmp_path,{'id':'account','name':'Account'})
    assert browser.put(PREFIX+'/harnesses/fixture',json=spec).status_code==200
    response=browser.post(PREFIX+'/harnesses/fixture/auth/start',json={})
    assert response.status_code==200,response.text
    state=wait_phase(browser,'waiting')
    assert state['interaction']['requiresConsent']
    setup=gateway.harness_catalog.provider_setup
    private=setup.auth_state(setup.spec('fixture'),'another-owner')
    assert private['flowId'] is None and private['interaction'] is None
    stale=browser.post(PREFIX+'/harnesses/fixture/auth/respond',json={'flowId':'stale','interactionId':'consent','response':{'type':'browser','action':'accept'}})
    assert stale.status_code==409
    result=browser.post(PREFIX+'/harnesses/fixture/auth/respond',json={'flowId':state['flowId'],'interactionId':'consent','response':{'type':'browser','action':'accept'}})
    assert result.status_code==200,result.text
    wait_phase(browser,'succeeded')
    assert setup.snapshots['fixture']['models'][0]['slug']=='account-model'


def test_credential_signin_saves_masked_values_and_reconnects(client,tmp_path):
    browser,gateway=client
    spec=fake_acp(tmp_path,{'id':'api-key','name':'API key','type':'env_var','vars':[{'name':'FIXTURE_KEY','description':'API key'}]})
    assert browser.put(PREFIX+'/harnesses/fixture',json=spec).status_code==200
    assert browser.post(PREFIX+'/harnesses/fixture/auth/start',json={}).status_code==200
    state=wait_phase(browser,'waiting')
    result=browser.post(PREFIX+'/harnesses/fixture/auth/respond',json={'flowId':state['flowId'],'interactionId':'credentials','response':{'type':'credentials','values':{'FIXTURE_KEY':'fixture-only-secret'}}})
    assert result.status_code==200 and 'fixture-only-secret' not in result.text
    wait_phase(browser,'succeeded')
    saved=next(s for s in gateway.control_store.harnesses() if s.id=='fixture')
    assert saved.environment['FIXTURE_KEY']=='fixture-only-secret'
    assert 'fixture-only-secret' not in browser.get(PREFIX+'/harnesses?probe=false&details=true').text
    bad=browser.post(PREFIX+'/harnesses/fixture/auth/respond',json={'flowId':'stale','interactionId':'terminal','response':{'type':'terminal','data':'fixture-only-secret','size':{'rows':0,'cols':1}}})
    assert bad.status_code==422 and 'fixture-only-secret' not in bad.text


def test_provider_api_key_and_model_preferences_survive_store_reload(client):
    browser,gateway=client
    spec={'id':'agy-fixture','kind':'acp','registry_agent_id':'antigravity-acp','auth_method':'gemini-api-key','api_key':'fixture-only-secret','hidden_models':['hidden'],'favorite_models':['favorite'],'model_order':['favorite','hidden']}
    result=browser.put(PREFIX+'/harnesses/agy-fixture',json=spec)
    assert result.status_code==200 and 'fixture-only-secret' not in result.text
    edited={**result.json(),'name':'Renamed'}
    assert browser.put(PREFIX+'/harnesses/agy-fixture',json=edited).status_code==200
    stored=next(s for s in gateway.control_store.harnesses() if s.id=='agy-fixture')
    assert stored.api_key=='fixture-only-secret' and stored.favorite_models==['favorite']


def test_project_execution_and_settings_share_only_the_runtime_coordinator(client):
    _,gateway=client
    setup=gateway.harness_catalog.provider_setup
    assert gateway.platform.registry.provider_setup is setup
    spec=models.HarnessSpec(id='fixture',kind='acp',registry_agent_id='codex-acp')
    with setup.lock:setup.active['codex-acp']=1
    with pytest.raises(operations.SetupError,match='finish'):
        setup.start_install(spec,'owner')
    assert not setup.installs


def test_antigravity_signin_uses_the_method_saved_in_its_configuration(client):
    _,gateway=client
    setup=gateway.harness_catalog.provider_setup
    spec=models.HarnessSpec(id='agy-fixture',kind='acp',registry_agent_id='antigravity-acp')
    assert setup.auth_state(spec,'owner')['methods'][0]['id']=='oauth-personal'
    with pytest.raises(operations.SetupError,match='settings first'):
        setup.start_auth(spec,'owner','gemini-api-key')
    assert not setup.auth
    spec=spec.model_copy(update={'api_key':'fixture-only-secret'})
    assert not setup.profiles.cached(spec)
    assert setup.profiles.cached(spec.model_copy(update={'auth_method':'gemini-api-key'}))
