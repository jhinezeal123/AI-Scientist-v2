"""Agent/model presets and their configured harness catalog."""
from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api_support import authenticate, control_store, gateway, ConflictRoute
from .models import HarnessSpec
from .presets import AgentPreset, Presets
from .harness_settings import HarnessSettings


class PresetRoute(ConflictRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def run(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                # FastAPI's default response echoes rejected input, including API keys.
                errors = [{'loc': error['loc'], 'msg': error['msg']} for error in exc.errors()]
                return JSONResponse({'detail': errors}, status_code=422)
        return run


def preset_service(request):
    owner = gateway(request)
    return Presets(owner.harness_catalog.store, default_model=getattr(owner.codex_runtime, 'model', None))


def create_preset_router():
    router = APIRouter(prefix='/api/agent-management', tags=['Agent presets'], route_class=PresetRoute)

    @router.get('/agent-presets')
    def presets(request: Request):
        authenticate(request)
        return preset_service(request).list()

    @router.put('/agent-presets/{identifier}')
    def save(identifier: str, body: AgentPreset, request: Request):
        authenticate(request, 'admin', human=True)
        if identifier != body.id:
            raise ValueError('Preset ID mismatch')
        return preset_service(request).put(body)

    @router.delete('/agent-presets/{identifier}')
    def delete(identifier: str, request: Request):
        authenticate(request, 'admin', human=True)
        preset_service(request).delete(identifier)
        return {'removed': identifier}

    @router.get('/harnesses')
    def harnesses(request: Request, details: bool = False, probe: bool = True):
        who = authenticate(request)
        if details:
            who.require('admin', human=True)
        catalog = gateway(request).harness_catalog
        settings = HarnessSettings(catalog)
        return [{'spec': settings.public(s, details=details),
                 'probe': settings.check(s) if probe else None} for s in catalog.store.harnesses() if not s.archived]

    @router.put('/harnesses/{identifier}')
    def configure(identifier: str, body: HarnessSpec, request: Request):
        authenticate(request, 'admin', human=True)
        if identifier != body.id:
            raise ValueError('Harness ID mismatch')
        return HarnessSettings(gateway(request).harness_catalog).put(body)

    @router.post('/harnesses/{identifier}/probe')
    def check(identifier: str, body: HarnessSpec, request: Request):
        authenticate(request, 'admin', human=True)
        if identifier != body.id:
            raise ValueError('Harness ID mismatch')
        return HarnessSettings(gateway(request).harness_catalog).check(body)

    @router.post('/harnesses/{identifier}/models')
    def discover_models(identifier: str, body: HarnessSpec, request: Request):
        authenticate(request, 'admin', human=True)
        if identifier != body.id:
            raise ValueError('Harness ID mismatch')
        owner = gateway(request)
        settings = HarnessSettings(owner.harness_catalog)
        from .harness_models import HarnessModels
        return HarnessModels(owner.harness_catalog, owner.workspace_root).discover(settings.resolve_draft(body))

    @router.post('/harnesses/dsh/import')
    def import_dsh(request: Request):
        authenticate(request, 'admin', human=True)
        from .dsh import install_local_profile
        spec = install_local_profile(gateway(request).workspace_root)
        control_store(request).put_harness(spec)
        return spec.model_dump()

    from .provider_api import create_provider_router
    router.include_router(create_provider_router(PresetRoute))
    return router
