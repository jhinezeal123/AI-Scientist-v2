"""Private account lifecycle, shared Settings cache and explicit cookie recovery."""
import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_scientist.workbench.accounts import AccountCatalog
from ai_scientist.workbench.kaggle_settings import KaggleProxySettings
from ai_scientist.workbench.settings_api import settings_router
from ai_scientist.workbench.store import StoreConflict


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[2] / 'kaggle mcp'
    monkeypatch.syspath_prepend(str(source))
    import account_admin, account_store, web_session
    profiles = tmp_path / 'profiles'
    profiles.mkdir()
    for field, value in [('BASE', tmp_path), ('PROFILES', profiles), ('REGISTRY', profiles/'accounts.json'),
                         ('CREDENTIALS', profiles/'credentials.json')]:
        monkeypatch.setattr(account_store, field, value)
    monkeypatch.setattr(web_session, 'protect_acl', lambda *a, **kw: None)
    monkeypatch.setattr(account_admin, 'token_username', lambda token: 'alice')
    return account_admin, account_store, profiles


def test_add_validates_identity_and_remove_permanently_erases_all_private_files(bundle, monkeypatch):
    admin, store, profiles = bundle
    result = admin.add_account('KGAT_fixture_secret_token', 'alice', 'private-password')
    assert result == {'account': 'alice.txt', 'username': 'alice', 'created': True}
    profile = profiles/'alice'
    (profile/'web-session.json').write_text('private-cookie')
    (profile/'browser').mkdir()
    (profile/'browser'/'password-db').write_text('private-browser-data')
    assert store.credentials('alice.txt')['kaggle_password'] == 'private-password'
    assert 'private' not in json.dumps(AccountCatalog(profiles.parent,'alice.txt').list())
    monkeypatch.setattr(admin.account_runtime, 'account_idle', lambda *a, **kw: {'idle': True, 'active_session_count': 0})
    assert admin.remove_account('alice.txt')['permanent'] is True
    assert not profile.exists()
    assert not store.load_registry()['accounts']
    assert not store.read_json(store.CREDENTIALS, {})['accounts']
    assert not list(store.token_files())


def test_wrong_token_identity_never_writes_profile_or_password(bundle, monkeypatch):
    admin, store, profiles = bundle
    monkeypatch.setattr(admin, 'token_username', lambda token: 'mallory')
    with pytest.raises(ValueError, match='không thuộc'):
        admin.add_account('KGAT_fixture_secret_token', 'alice', 'private-password')
    assert not (profiles/'alice').exists() and not store.CREDENTIALS.exists()


def test_removal_blocks_live_sessions_and_paths_outside_profile_root(bundle, monkeypatch):
    admin, store, profiles = bundle
    admin.add_account('KGAT_fixture_secret_token', 'alice', 'private-password')
    monkeypatch.setattr(admin.account_runtime, 'account_idle', lambda *a, **kw: {'idle': False, 'active_session_count': 1})
    with pytest.raises(ValueError, match='session'):
        admin.remove_account('alice.txt')
    assert (profiles/'alice'/'token.txt').exists()
    document = store.load_registry()
    document['accounts']['alice.txt']['alias'] = '..'
    store.write_json(store.REGISTRY, document)
    with pytest.raises(ValueError, match='ngoài bundle'):
        admin.remove_account('alice.txt')
    assert store.CREDENTIALS.exists()


def test_cookie_renewal_only_for_proven_invalid_cookie_and_checks_identity(bundle, monkeypatch):
    admin, _, _ = bundle
    admin.add_account('KGAT_fixture_secret_token', 'alice', 'private-password')
    calls = []
    monkeypatch.setattr(admin.account_runtime,'auto_login_core',lambda account: calls.append(account) or {'status':'ok'})
    monkeypatch.setattr(admin.web_session,'identify_user',lambda path:'alice')
    monkeypatch.setattr(admin,'overview',lambda account:{'cookie':{'status':'unverified'}})
    assert admin.check_cookie('alice.txt')['status'] == 'unavailable' and not calls
    monkeypatch.setattr(admin,'overview',lambda account:{'cookie':{'status':'valid'}})
    assert admin.check_cookie('alice.txt')['status'] == 'valid' and not calls
    samples = iter([{'cookie':{'status':'expired'}},{'cookie':{'status':'valid'}}])
    monkeypatch.setattr(admin,'overview',lambda account:next(samples))
    result = admin.check_cookie('alice.txt')
    assert result['status']=='renewed' and result['was_expired'] and calls==['alice.txt']


def test_quota_and_sessions_preserve_unknown_values_and_every_version(bundle):
    admin, _, _ = bundle
    data = admin._quota_from_cookie('alice.txt','alice',{'gpuQuota':{'timeUsed':'3600s','totalTimeAllowed':'108000s'},
        'tpuQuota':{'totalTimeAllowed':'NaNs'}})
    assert data['gpu']=={'used_h':1.0,'remaining_h':29.0,'total_h':30.0} and 'tpu' not in data
    parsed=admin.parse_active_sessions({'totalCount':2,'sessions':[
        {'kernelId':5,'kernelRunId':101,'versionNumber':1,'accelerator':'NvidiaTeslaT4'},
        {'kernelId':5,'kernelRunId':102,'versionNumber':2,'accelerator':'TPU_V6E_8'}]}, {5:'alice/notebook'})
    assert [row['kernel_session_id'] for row in parsed['sessions']]==[101,102]
    with pytest.raises(ValueError):
        admin.parse_active_sessions({'totalCount':0,'sessions':[{}]})


def test_session_enrichment_failure_does_not_hide_active_sessions(bundle, monkeypatch):
    admin, _, _ = bundle
    admin.add_account('KGAT_fixture_secret_token', 'alice', 'private-password')
    monkeypatch.setattr(admin.web_session, 'cookie_status', lambda path: {'expired': False})
    monkeypatch.setattr(admin.web_session, 'identify_user', lambda path: 'alice')
    import cookie_client
    def call(method, arguments, timeout):
        if method.endswith('GetKernel'):
            raise TimeoutError()
        if method.endswith('ListKernelSessions'):
            return 200, {'totalCount': 1, 'sessions': [{'kernelId': 5, 'kernelRunId': 12}]}
        return 200, {}
    monkeypatch.setattr(cookie_client, '_client_for', lambda key: SimpleNamespace(call=call))
    result = admin.overview('alice.txt')
    assert result['sessions']['total_count'] == 1
    assert result['sessions']['sessions'][0]['kernel_session_id'] == 12
    assert result['sessions']['sessions'][0]['ref'] == ''


@pytest.mark.parametrize('readable', [True, False])
def test_readiness_returns_session_identity_for_capacity_without_hiding_unknown_versions(bundle, monkeypatch, readable):
    admin, _, _ = bundle
    admin.add_account('KGAT_fixture_secret_token', 'alice', 'private-password')
    monkeypatch.setattr(admin.web_session, 'cookie_status', lambda path: {'expired': False})
    monkeypatch.setattr(admin.web_session, 'identify_user', lambda path: 'alice')
    import cookie_client
    def call(method, arguments, timeout=None):
        if method.endswith('GetKernel'):
            if not readable:
                raise TimeoutError()
            return 200, {'author':{'userName':'alice'}, 'slug':'test-session'}
        assert method.endswith('ListKernelSessions')
        return 200, {'totalCount':2, 'sessions':[{'kernelId':5, 'kernelRunId':12}]}
    monkeypatch.setattr(cookie_client, '_client_for', lambda key: SimpleNamespace(call=call))
    observation = admin.account_runtime.account_readiness('alice.txt')
    assert observation['readiness'] == 'busy' and observation['active_session_count'] == 2
    assert observation['active_sessions'][0]['kernel_session_id'] == 12
    assert observation['active_sessions'][0]['ref'] == ('alice/test-session' if readable else '')


def test_proxy_refresh_picks_up_additions_removals_and_rotation(bundle, monkeypatch):
    admin, store, profiles=bundle
    monkeypatch.setattr('sys.argv',['proxy.py','8013'])
    source=Path(__file__).resolve().parents[2]/'kaggle mcp'/'proxy.py'
    spec=importlib.util.spec_from_file_location('test_settings_proxy',source)
    proxy=importlib.util.module_from_spec(spec);spec.loader.exec_module(proxy)
    assert not proxy.tokens
    admin.add_account('KGAT_fixture_secret_token','alice','private-password')
    proxy.refresh_tokens()
    assert [row[0] for row in proxy.tokens]==['alice.txt']
    proxy.tokens[0][2]=7
    proxy.refresh_tokens()
    assert proxy.tokens[0][2]==7
    (profiles/'alice'/'token.txt').write_text('KGAT_rotated_fixture_token_longer')
    proxy.refresh_tokens()
    assert proxy.tokens[0][1]=='KGAT_rotated_fixture_token_longer' and proxy.tokens[0][2]==0
    monkeypatch.setattr(admin.account_runtime,'account_idle',lambda *a,**kw:{'idle':True,'active_session_count':0})
    admin.remove_account('alice.txt');proxy.refresh_tokens()
    assert not proxy.tokens


def service_fixture(bundle, monkeypatch):
    admin, store, profiles = bundle
    admin.add_account('KGAT_fixture_secret_token','alice','private-password')
    catalog=AccountCatalog(profiles.parent,'alice.txt')
    calls=[]
    remote={'account':'alice.txt','username':'alice','observed_at':'now','cookie':{'status':'expired','expired':True},
            'quota':None,'sessions':None,'errors':[]}
    def call(action,args=None,cancelled=None):
        calls.append(action)
        if action=='cookie-check':
            remote.update(cookie={'status':'valid','expired':False},sessions={'total_count':0,'sessions':[]})
            return {'account':'alice.txt','status':'renewed','was_expired':True,'auto_login_attempted':True}
        return deepcopy(remote)
    working=SimpleNamespace(accounts=catalog,config=SimpleNamespace(kaggle_account_alias='alice.txt'),
        planner=SimpleNamespace(lock=asyncio.Lock()),_donor=lambda account:SimpleNamespace(account_admin=call))
    async def check_cookie(account):
        return call('cookie-check')
    working.check_account_cookie=check_cookie
    service=KaggleProxySettings(working)
    monkeypatch.setattr(service,'_known_runs',lambda:[])
    return service,calls


def test_snapshot_never_logs_in_cookie_job_is_single_and_cache_shared(bundle,monkeypatch):
    async def scenario():
        service,calls=service_fixture(bundle,monkeypatch)
        snapshot=await service.snapshot()
        assert snapshot['accounts'][0]['readiness']=='needs_login' and calls==['account-overview']
        await service.snapshot()
        assert len(calls)==1
        job=service.start_cookie_check()
        with pytest.raises(StoreConflict):service.start_cookie_check()
        await service.task
        assert job['state']=='completed' and job['accounts'][0]['status']=='renewed'
        assert calls.count('cookie-check')==1
        snapshot=await service.snapshot()
        assert snapshot['accounts'][0]['readiness']=='verified_idle'
        await service.close()
    asyncio.run(scenario())


def test_session_links_require_account_and_active_attempt_match():
    row={'ref':'alice/ai-scientist-ssh-abc','kernel_session_id':12}
    remote={'username':'alice','sessions':{'sessions':[row]}}
    run={'account':'alice.txt','record':{'stop_confirmed':False},'identity':{},'ref':row['ref'],
         'project_id':'p','project_name':'Project','run_id':'abc','run_title':'Run','run_state':'WORKING','href':'/?project=p&view=run&run=abc'}
    KaggleProxySettings._link_sessions('bob.txt',remote,[run]);assert row['workbench'] is None
    KaggleProxySettings._link_sessions('alice.txt',remote,[run]);assert row['workbench']['href']==run['href']
    run['record']['stop_confirmed']=True
    KaggleProxySettings._link_sessions('alice.txt',remote,[run]);assert row['workbench'] is None


def test_delete_blocks_queued_run_before_touching_kaggle_or_secrets(bundle,monkeypatch):
    async def scenario():
        service,calls=service_fixture(bundle,monkeypatch)
        monkeypatch.setattr(service,'_known_runs',lambda:[{'account':'alice.txt','record':{'stop_confirmed':False},'run_state':'QUEUED'}])
        with pytest.raises(StoreConflict,match='run'):
            await service.remove('alice.txt')
        assert not calls and bundle[1].read_token('alice.txt')=='KGAT_fixture_secret_token'
    asyncio.run(scenario())


def test_settings_invalid_secret_input_is_not_echoed_and_cross_origin_mutations_rejected():
    app=FastAPI();app.include_router(settings_router())
    with TestClient(app) as client:
        response=client.post('/api/settings/kaggle-proxy/accounts',json={'token':'KGAT_secret_example','password':'secret-password'})
        assert response.status_code==422 and 'secret' not in response.text and 'KGAT_secret' not in response.text
        response=client.post('/api/settings/kaggle-proxy/check-cookie',headers={'Origin':'https://outside.example'})
        assert response.status_code==403


def test_readiness_distinguishes_server_rejection_from_network_failure(bundle, monkeypatch):
    admin, _, _ = bundle
    admin.add_account('KGAT_fixture_secret_token', 'alice', 'private-password')
    invalid = {'value': False}
    monkeypatch.setattr(admin.web_session, 'cookie_status', lambda path: {'expired': invalid['value']})
    monkeypatch.setattr(admin.web_session, 'identify_user', lambda path: 'alice')
    def failed_probe(account, recover):
        raise RuntimeError('network failure')
    monkeypatch.setattr(admin.account_runtime, 'account_idle', failed_probe)
    with pytest.raises(RuntimeError):
        admin.account_runtime.account_readiness('alice.txt')
    def rejected_probe(account, recover):
        invalid['value'] = True
        raise RuntimeError('auth rejected')
    monkeypatch.setattr(admin.account_runtime, 'account_idle', rejected_probe)
    assert admin.account_runtime.account_readiness('alice.txt')['readiness'] == 'needs_login'
    invalid['value'] = False
    monkeypatch.setattr(admin.web_session, 'identify_user', lambda path: 'wrong-account')
    assert admin.account_runtime.account_readiness('alice.txt')['readiness'] == 'needs_login'
