"""Shared HTTP/authentication infrastructure; contains no feature policy."""
import os

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from .auth import DeviceAccess, remote_surface, transport_guard


def gateway(request):
    if not os.environ.get('AI_SCIENTIST_AGENT_CONTROL_TOKEN'):
        raise HTTPException(404, 'Agent management disabled. Set AI_SCIENTIST_AGENT_CONTROL_TOKEN when starting Workbench.')
    owner = getattr(getattr(request.app.state, 'runtime', None), 'runtime', None)
    if owner is None or not hasattr(type(owner), 'platform'):
        raise HTTPException(503, 'Agent gateway is unavailable')
    config = getattr(request.app.state, 'config', None)
    owner.protected_paths = tuple(p for p in (getattr(config, 'donor_root', None),) if p)
    owner.projects = getattr(request.app.state, 'store', None)
    return owner


def control_store(request):
    return gateway(request).control_store


def authenticate(request, scope='read', rig_id=None, *, human=False):
    return DeviceAccess(control_store(request)).authenticate(request, scope=scope, rig_id=rig_id, human=human)


def platform(request):
    owner = gateway(request)
    control = owner.platform
    control.context.projects = owner.projects
    return control


def access(request, scope='read', rig_id=None, *, human=False):
    principal = authenticate(request, scope, rig_id, human=human)
    control = gateway(request).team_platform(rig_id) if rig_id else platform(request)
    return control, principal


async def remote_boundary(request, call_next):
    # Private HTTPS must not expose the unpaired legacy Project API.
    if request.url.path != '/health' and remote_surface(request):
        try:
            transport_guard(request)
            path = request.url.path
            if path.startswith('/api/') and path != '/api/agent-management/pair/exchange':
                if not path.startswith('/api/agent-management/'):
                    raise HTTPException(403, 'Remote devices use the scoped multi-agent API')
                authenticate(request)
        except HTTPException as exc:
            return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    return await call_next(request)


class ConflictRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def run(request):
            try:
                return await handler(request)
            except KeyError:
                return JSONResponse({'detail': 'Team, seat or resource not found'}, status_code=404)
            except ValueError as exc:
                return JSONResponse({'detail': str(exc)[:2000]}, status_code=409)
        return run
