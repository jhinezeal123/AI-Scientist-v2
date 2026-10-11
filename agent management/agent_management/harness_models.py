"""Model discovery for one configured agent. Metadata only, no prompt or turn."""
import json
from pathlib import Path
import queue
import re

from .acp_sessions import AcpHarness, RpcChannel
from .harnesses import NativeHarness


class CodexCatalogChannel(RpcChannel):
    """Codex app-server uses JSON-RPC messages without the jsonrpc member."""
    def pump(self):
        self.guard()
        try:
            message = self.inbox.get(timeout=.05)
        except queue.Empty:
            if self.proc.poll() is not None:
                raise RuntimeError('Agent exited during model discovery')
            return
        if not isinstance(message, dict):
            raise ValueError('Invalid model catalog response')
        if 'method' in message:
            if 'id' in message:
                self.send({'id': message['id'], 'error': {'code': -32601, 'message': 'Metadata discovery only'}})
        elif 'id' in message:
            if len(self.pending) > 100:
                raise ValueError('Too many catalog responses')
            self.pending[message['id']] = message


def flatten_choices(options):
    for option in options:
        if isinstance(option, dict):
            if 'value' in option:
                yield option
            yield from flatten_choices(option.get('options', []))


def version_tuple(value):
    match = re.search(r'\b(\d+)\.(\d+)\.(\d+)\b', value or '')
    return tuple(map(int, match.groups())) if match else None


class HarnessModels:
    def __init__(self, catalog, workspace):
        self.catalog, self.workspace = catalog, Path(workspace)

    def codex(self, spec):
        adapter = NativeHarness(spec, codex=self.catalog.codex)
        channel = CodexCatalogChannel([adapter.executable(), 'app-server'], self.workspace, 25,
                                     lambda: False, lambda _: {}, lambda _: None, adapter.environment())
        try:
            initialized = channel.rpc('initialize', {
                'clientInfo': {'name': 'workbench-settings', 'version': '1.0.0'},
                'capabilities': {'experimentalApi': True, 'explicitGatewayOauth': True}})
            channel.send({'method': 'initialized'})
            account = channel.rpc('account/read', {'refreshToken': False})
            if account.get('requiresOpenaiAuth') and not account.get('account'):
                raise ValueError('Agent sign-in required')
            models, cursor = [], None
            for _ in range(10):
                response = channel.rpc('model/list', {'cursor': cursor} if cursor else {})
                for row in response.get('data', []):
                    if not isinstance(row, dict) or not row.get('model'):
                        continue
                    descriptors = []
                    efforts = row.get('supportedReasoningEfforts', [])
                    if efforts:
                        descriptors.append({'id': 'reasoningEffort', 'label': 'Reasoning', 'type': 'select',
                            'options': [{'id': e['reasoningEffort'], 'label': e['reasoningEffort'].title(),
                                         'isDefault': e['reasoningEffort'] == row.get('defaultReasoningEffort')}
                                        for e in efforts if isinstance(e, dict) and e.get('reasoningEffort')]})
                    models.append({'slug': row['model'], 'name': row.get('displayName') or row['model'],
                                   'isCustom': False, 'isDefault': bool(row.get('isDefault')),
                                   'capabilities': {'optionDescriptors': descriptors}})
                cursor = response.get('nextCursor')
                if not cursor:
                    break
            version = version_tuple(initialized.get('userAgent'))
            return {'models': models, 'source': 'agent', 'installed': True,
                    'version': '.'.join(map(str, version)) if version else None,
                    'auth': 'authenticated' if account.get('account') else 'unknown'}
        finally:
            channel.close()

    def acp(self, spec):
        if spec.registry_agent_id:
            return self.catalog.provider_setup.metadata(spec)
        adapter = AcpHarness(spec)
        from .processes import private_environment
        environment = {**private_environment(), **spec.environment}
        if spec.managed_home:
            environment['DSH_HOME'] = spec.managed_home
        channel = RpcChannel([adapter.executable(), *spec.args], self.workspace, 25, lambda: False,
            lambda _: {'error': {'code': -32601, 'message': 'Metadata discovery only'}}, lambda _: None, environment)
        try:
            adapter.initialize(channel)
            session = channel.rpc('session/new', {'cwd': str(self.workspace.resolve()), 'mcpServers': []})
            model_option = next((o for o in session.get('configOptions', []) if o.get('category') == 'model' or o.get('id') == 'model'), None)
            choices = flatten_choices(model_option.get('options', [])) if model_option else []
            models = [{'slug': row['value'], 'name': row.get('name') or row['value'], 'isCustom': False,
                       'isDefault': row['value'] == model_option.get('currentValue')} for row in choices]
            if not models:
                legacy = session.get('models', {})
                models = [{'slug': row['modelId'], 'name': row.get('name') or row['modelId'], 'isCustom': False,
                           'isDefault': row['modelId'] == legacy.get('currentModelId')}
                          for row in legacy.get('availableModels', []) if row.get('modelId')]
            return {'models': models, 'source': 'agent', 'installed': True, 'auth': 'unknown'}
        finally:
            channel.close()

    def claude(self, spec):
        adapter = NativeHarness(spec, codex=self.catalog.codex)
        probe = adapter.probe()
        version = version_tuple(probe.get('version'))
        manifest = json.loads((Path(__file__).parent/'vendor/t3code/model-manifest.json').read_text(encoding='utf-8'))
        catalog = manifest['providers']['claudeAgent']
        models = []
        for row in catalog['models']:
            compatibility = row.get('adapter', {}).get('claudeCode', {})
            minimum = version_tuple(compatibility.get('minVersion'))
            maximum = version_tuple(compatibility.get('maxVersionExclusive'))
            if version and ((minimum and version < minimum) or (maximum and version >= maximum)):
                continue
            profile = catalog['profiles'].get(row.get('profile'), {})
            models.append({'slug': row['slug'], 'name': row['name'], 'aliases': row.get('aliases', []),
                           'isCustom': False, 'isLegacy': row.get('status') == 'legacy',
                           'isDefault': row['slug'] == catalog.get('defaults', {}).get('chat'),
                           'capabilities': profile.get('capabilities', {'optionDescriptors': []})})
        return {'models': models, 'source': 't3-catalog', 'installed': probe['ready'],
                'version': '.'.join(map(str, version)) if version else None, 'auth': 'unknown'}

    def discover(self, spec):
        try:
            if spec.kind == 'native_codex':
                result = self.codex(spec)
            elif spec.kind == 'native_claude':
                result = self.claude(spec)
            elif spec.kind == 'acp':
                result = self.acp(spec)
            else:
                result = {'models': [{'slug': slug, 'name': slug, 'isCustom': False} for slug in spec.models],
                          'source': 'configured', 'installed': NativeHarness(spec).probe()['ready'], 'auth': 'unknown'}
            result.setdefault('status', 'ready' if result['installed'] else 'warning')
            if not result['installed']:
                result.setdefault('message', 'CLI not detected. Check the binary path.')
        except (OSError, ValueError, RuntimeError, TimeoutError):
            # Provider protocol errors may contain credential-bearing details.
            result = {'models': [], 'source': 'unavailable', 'installed': False, 'auth': 'unknown',
                      'status': 'error', 'message': 'Could not read models. Check the agent binary, profile and sign-in, then refresh.'}
        seen, models = set(), []
        for row in result['models']:
            slug = row.get('slug')
            if isinstance(slug, str) and 0 < len(slug) <= 256 and slug not in seen:
                seen.add(slug)
                models.append(row)
        for entry in spec.custom_models:
            if entry.slug not in seen:
                models.append({**entry.model_dump(exclude_none=True), 'isCustom': True})
        result['models'] = models[:200]
        return result
