"""Administrative provider configuration, masking and non-session checks."""
from .models import HarnessSpec
import json
import os
from pathlib import Path

REDACTED = '__WORKBENCH_STORED_SECRET__'


class HarnessSettings:
    def __init__(self, catalog):
        self.catalog = catalog

    def public(self, spec, *, details=False):
        value = spec.model_dump()
        value['models'] = spec.models if details else self.models(spec)
        if details:
            sensitive = set(spec.environment_sensitive) if spec.environment_sensitive is not None else set(spec.environment)
            value['environment'] = {key: REDACTED if key in sensitive else content for key, content in spec.environment.items()}
            value['api_key'] = REDACTED if spec.api_key else ''
        else:
            for key in ('executable', 'args', 'managed_home', 'environment', 'api_key'):
                value.pop(key)
        return value

    def models(self, spec):
        models = spec.models[:]
        if spec.kind == 'native_codex':
            default = getattr(self.catalog.codex, 'model', None)
            if default:
                models.append(default)
            # Codex's installed CLI keeps the last server model catalog here.
            # Reading the cache does not start a session or spend model tokens.
            home = Path(spec.config_directory or spec.environment.get('CODEX_HOME') or os.environ.get('CODEX_HOME') or Path.home()/'.codex').expanduser()
            cache = home/'models_cache.json'
            try:
                if not cache.is_symlink() and cache.stat().st_size <= 2_000_000:
                    for model in json.loads(cache.read_text(encoding='utf-8')).get('models', []):
                        slug = model.get('slug')
                        if model.get('visibility') != 'hide' and isinstance(slug, str) and 0 < len(slug) <= 256:
                            models.append(slug)
            except (OSError, ValueError, AttributeError, TypeError):
                pass
        elif spec.kind == 'native_claude':
            models.extend(['sonnet', 'opus', 'haiku'])
        return list(dict.fromkeys(models))[:100]

    def resolve_draft(self, spec):
        previous = next((h for h in self.catalog.store.harnesses() if h.id == spec.id), None)
        environment = {}
        for key, value in spec.environment.items():
            if value == REDACTED:
                if previous is None or key not in previous.environment:
                    raise ValueError('Stored environment value is unavailable')
                value = previous.environment[key]
            environment[key] = value
        if spec.kind.startswith('native_') and spec.args:
            raise ValueError('Literal launch arguments are supported for ACP and CLI JSON agents')
        api_key=spec.api_key
        if api_key==REDACTED:
            if previous is None: raise ValueError('Stored provider API key is unavailable')
            api_key=previous.api_key
        return spec.model_copy(update={'environment': environment,'api_key':api_key})

    def put(self, spec):
        spec = self.resolve_draft(spec)
        if spec.archived:
            from .presets import Presets
            if any(pair['harness'] == spec.id for pair in Presets(self.catalog.store).list()):
                raise ValueError('Remove the presets using this agent before deleting it')
        self.catalog.store.put_harness(spec)
        return self.public(spec, details=True)

    def check(self, spec):
        # No session, prompt, model call, install or persistent write.
        spec = self.resolve_draft(spec)
        from .harnesses import NativeHarness
        if spec.kind == 'acp':
            from .acp_sessions import AcpHarness
            if spec.registry_agent_id:
                try:
                    command,args,variables,_=self.catalog.provider_setup.installations.resolve(spec)
                    spec=spec.model_copy(update={'executable':command,'args':args})
                except ValueError:
                    return {'id':spec.id,'kind':'acp','ready':False,'capabilities':{}}
            adapter=AcpHarness(spec)
        else:
            adapter = NativeHarness(spec, codex=self.catalog.codex)
        probe = adapter.probe()
        # Probe output can contain arbitrary stdout from a configured executable.
        # Never return it to clients alongside credentials.
        probe.pop('version', None)
        return probe
