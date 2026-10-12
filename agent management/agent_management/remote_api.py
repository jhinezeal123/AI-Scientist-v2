"""Personal-device pairing and credential administration."""
from fastapi import APIRouter, Request
from pydantic import Field

from .api_support import authenticate, control_store, gateway, ConflictRoute
from .auth import DeviceAccess, transport_guard
from .auth_api import session_response
from .models import StrictModel
from .remote import RemoteDevices


class Pair(StrictModel):
    scopes: list[str] = Field(default_factory=lambda: ['read'])
    rig_ids: list[str] = Field(min_length=1, max_length=100)


class Exchange(StrictModel):
    pairing_id: str = Field(max_length=64)
    code: str = Field(max_length=256)
    name: str = Field(min_length=1, max_length=120)


def create_remote_router():
    router = APIRouter(prefix='/api/agent-management', tags=['Remote devices'], route_class=ConflictRoute)

    @router.post('/pair')
    def pair(body: Pair, request: Request):
        authenticate(request, 'admin', human=True)
        if not getattr(request.app.state, 'legacy_teams', False) and not set(body.scopes) <= {'read', 'research'}:
            raise ValueError('Remote devices may view projects and optionally operate their workflows')
        for rig_id in body.rig_ids:
            if rig_id != '*':
                owner = gateway(request)
                if owner.projects and any(p['id'] == rig_id for p in owner.projects.list_projects()):
                    owner.projects.project(rig_id)
                else:
                    # Existing paired devices can still be managed with the archived API.
                    if not getattr(request.app.state, 'legacy_teams', False):
                        raise ValueError('Choose an existing project')
                    owner.team_platform(rig_id).store.rig(rig_id)
        return RemoteDevices(control_store(request)).pairing(scopes=body.scopes, rig_ids=body.rig_ids)

    @router.post('/pair/exchange')
    def exchange(body: Exchange, request: Request):
        transport_guard(request)
        result = RemoteDevices(control_store(request)).exchange(body.pairing_id, body.code, body.name)
        return session_response(result, request)

    @router.get('/devices')
    def devices(request: Request):
        authenticate(request, 'admin', human=True)
        return DeviceAccess(control_store(request)).devices()

    @router.delete('/devices/{device_id}')
    def revoke(device_id: str, request: Request):
        authenticate(request, 'admin', human=True)
        DeviceAccess(control_store(request)).revoke(device_id)
        return {'revoked': device_id}

    return router
