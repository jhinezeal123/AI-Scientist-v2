"""Feature isolation, copied values and scoped authority without external calls."""
import ast
import importlib
from pathlib import Path
import re

import pytest

from tests.workbench.test_agent_team_api import client, repository, P, Gateway
from tests.workbench.test_project_agents import bind

PREFIX = '/api/agent-management'


def test_settings_do_not_construct_team_scheduler(client, monkeypatch):
    browser, gateway = client

    def unavailable(_):
        raise AssertionError('Settings must not construct a team scheduler')

    monkeypatch.setattr(Gateway, 'platform', property(unavailable))
    assert browser.get(PREFIX+'/identity').status_code == 200
    assert browser.get(PREFIX+'/integrations/slack').status_code == 200
    assert browser.put(PREFIX+'/integrations/slack', json={'enabled':True,'channel':'C123'}).status_code == 200
    assert browser.get(PREFIX+'/devices').status_code == 200
    assert browser.post(PREFIX+'/pair', json={'scopes':['read'],'rig_ids':['*']}).status_code == 200
    assert browser.get(PREFIX+'/agent-presets').status_code == 200
    assert browser.put(PREFIX+'/agent-presets/copied', json={
        'id':'copied','name':'Independent pair','harness':'codex','model':'fixture-model'
    }).status_code == 200
    assert gateway._platform is None


@pytest.mark.parametrize('failed_feature,method,failed_endpoint', [
    ('slack','SlackIntegration', '/integrations/slack'),
    ('presets','Presets', '/agent-presets'),
    ('remote','RemoteDevices', '/pair'),
    ('project_teams','ProjectTeams', '/projects/{project}/team'),
])
def test_one_feature_failure_does_not_block_others(client, repository, monkeypatch,
                                                  failed_feature, method, failed_endpoint):
    browser, gateway = client
    projects = bind(browser, gateway, repository)
    project = projects.create_project('Feature boundary')
    team = browser.post(PREFIX+'/projects/'+project['id']+'/team').json()
    before = browser.get(PREFIX+'/teams/'+team['id']).json()

    def fail(*args, **kwargs):
        raise ValueError('Fixture feature unavailable')

    cls = getattr(importlib.import_module(P+'.'+failed_feature), method)
    monkeypatch.setattr(cls, '__init__', fail)
    endpoint = PREFIX+failed_endpoint.format(project=project['id'])
    response = browser.post(endpoint, json={'scopes':['read'],'rig_ids':[team['id']]}) if failed_feature == 'remote' else browser.get(endpoint)
    assert response.status_code == 409
    for module, path in [('slack','/integrations/slack'), ('presets','/agent-presets'),
                         ('project_teams','/projects/'+project['id']+'/team')]:
        if module != failed_feature:
            assert browser.get(PREFIX+path).status_code == 200
    assert browser.get(PREFIX+'/devices').status_code == 200
    if failed_feature != 'remote':
        assert browser.post(PREFIX+'/pair', json={'scopes':['read'],'rig_ids':[team['id']]}).status_code == 200
    assert browser.get(PREFIX+'/teams/'+team['id']).json() == before


def test_preset_slack_and_remote_mutations_do_not_rewrite_project_team(client, repository):
    browser, gateway = client
    projects = bind(browser, gateway, repository)
    project = projects.create_project('Copied preset')
    original = {'id':'default','name':'Initial pair','harness':'codex','model':'model-v1'}
    assert browser.put(PREFIX+'/agent-presets/default', json=original).status_code == 200
    team = browser.post(PREFIX+'/projects/'+project['id']+'/team').json()
    assert team['spec']['seats'][0]['model'] == 'model-v1'
    pairing = browser.post(PREFIX+'/pair', json={'scopes':['read'],'rig_ids':[team['id']]}).json()
    device = browser.post(PREFIX+'/pair/exchange', json={
        'pairing_id':pairing['pairing_id'],'code':pairing['code'],'name':'Fixture device'
    }).json()
    devices_before = browser.get(PREFIX+'/devices').json()
    assert browser.put(PREFIX+'/agent-presets/default', json={**original,'model':'model-v2'}).status_code == 200
    assert browser.put(PREFIX+'/agent-presets/remaining', json={**original,'id':'remaining'}).status_code == 200
    assert browser.delete(PREFIX+'/agent-presets/default').status_code == 200
    slack = {'enabled':True,'channel':'C123'}
    assert browser.put(PREFIX+'/integrations/slack', json=slack).status_code == 200
    assert browser.get(PREFIX+'/devices').json() == devices_before
    presets_before = browser.get(PREFIX+'/agent-presets').json()
    assert browser.delete(PREFIX+'/devices/'+device['device_id']).status_code == 200
    assert browser.get(PREFIX+'/agent-presets').json() == presets_before
    assert browser.get(PREFIX+'/integrations/slack').json()['channel'] == slack['channel']
    assert browser.get(PREFIX+'/teams/'+team['id']).json() == team
    assert gateway.team_platform(team['id']).store.path.parent == projects.directory(project['id'])/'agents'


def test_remote_read_device_cannot_mutate_settings_or_team_configuration(client, repository):
    browser, gateway = client
    projects = bind(browser, gateway, repository)
    project = projects.create_project('Scoped remote')
    team = browser.post(PREFIX+'/projects/'+project['id']+'/team').json()
    pair = browser.post(PREFIX+'/pair', json={'scopes':['read'],'rig_ids':[team['id']]}).json()
    browser.headers.pop('Authorization')
    device = browser.post(PREFIX+'/pair/exchange', json={
        'pairing_id':pair['pairing_id'],'code':pair['code'],'name':'Read-only device'
    }).json()
    browser.headers['X-Agent-CSRF'] = device['csrf']
    assert browser.get(PREFIX+'/teams/'+team['id']).status_code == 200
    assert browser.get(PREFIX+'/integrations/slack').status_code == 403
    assert browser.put(PREFIX+'/agent-presets/default', json={
        'id':'default','name':'Forbidden','harness':'codex','model':None
    }).status_code == 403
    assert browser.post(PREFIX+'/projects/'+project['id']+'/team').status_code == 403
    assert browser.get(PREFIX+'/devices').status_code == 403


def test_feature_modules_keep_dependency_boundaries():
    root = Path(__file__).resolve().parents[2]
    domain = root/'agent management/agent_management'
    # Domain policy may use contracts and persistence, never another feature.
    features = {'slack','remote','presets','project_teams','team_api'}
    for feature in features:
        imports = {node.module for node in ast.walk(ast.parse((domain/(feature+'.py')).read_text(encoding='utf-8')))
                   if isinstance(node, ast.ImportFrom) and node.level == 1}
        assert not imports & (features-{feature}), (feature, imports)
    ui = root/'workbench-ui/src'
    allowed = {
        'SlackSettings.tsx': {'react','./slackApi','./useAgentAction'},
        'PresetSettings.tsx': {'react','lucide-react','./agentPresets','./PresetEditor','./T3ProviderSetup','./T3AddProviderDialog','./providerModelOptions'},
        'PresetEditor.tsx': {'react','./agentPresets','./T3ProviderSetup','./providerModelOptions','./useAgentAction'},
        'T3ProviderSetup.tsx': {'./agentPresets'},
        'providerModelOptions.ts': {'./agentPresets'},
        'T3AddProviderDialog.tsx': {'react','@base-ui/react/radio','@base-ui/react/radio-group','./agentPresets','./T3ProviderSetup','./useAgentAction'},
        'RemoteSettings.tsx': {'react','./agentAuth','./remoteApi','./useAgentAction'},
        'RemotePairing.tsx': {'react','./remoteApi','./useAgentAction'},
        'ProjectWorkflow.tsx': {'react','./AgentAccess','./agentApi','./agentPresets','./projectWorkflows'},
        'AgentAccess.tsx': {'react','./agentApi','./agentAuth'},
    }
    for file, permitted in allowed.items():
        imports = set(re.findall(r"from\s+['\"]([^'\"]+)['\"]", (ui/file).read_text(encoding='utf-8')))
        if file in {'PresetSettings.tsx','PresetEditor.tsx','T3ProviderSetup.tsx','T3AddProviderDialog.tsx','providerModelOptions.ts'}:
            imports = {name for name in imports if not name.startswith('./vendor/t3code/')}
        assert imports <= permitted, (file, imports-permitted)
