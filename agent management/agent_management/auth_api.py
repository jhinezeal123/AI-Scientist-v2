"""Browser sessions and scoped credentials shared by all features."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .api_support import authenticate, control_store, gateway, ConflictRoute
from .auth import DeviceAccess, COOKIE, digest, loopback, remote_surface


def session_response(result, request):
    response = JSONResponse({k: v for k, v in result.items() if k != 'token'})
    response.set_cookie(COOKIE, result['token'], max_age=30*86400, httponly=True,
                        secure=request.url.scheme == 'https', samesite='strict', path='/api/agent-management')
    response.headers['Cache-Control'] = 'no-store'
    return response


def create_auth_router(*, include_legacy_teams=False):
    router = APIRouter(prefix='/api/agent-management', tags=['Agent access'], route_class=ConflictRoute)

    @router.get('/identity')
    def identity(request: Request):
        who = authenticate(request)
        cookie = request.cookies.get(COOKIE)
        return {'id': who.id, 'scopes': sorted(who.scopes), 'rig_ids': sorted(who.rig_ids), 'agent': who.agent,
                'csrf': digest(cookie+':csrf') if cookie and not request.headers.get('authorization') else None}

    @router.post('/local-session')
    def local_session(request: Request):
        who = authenticate(request, 'admin', human=True)
        if who.id != 'local-operator' or not loopback(request) or remote_surface(request):
            raise HTTPException(403, 'Local session requires the local control token')
        return session_response(DeviceAccess(control_store(request)).local_session(), request)

    @router.post('/logout')
    def logout(request: Request):
        who = authenticate(request, human=True)
        if who.id != 'local-operator':
            DeviceAccess(control_store(request)).revoke(who.id)
        response = JSONResponse({'signed_out': True}, headers={'Cache-Control': 'no-store'})
        response.delete_cookie(COOKIE, path='/api/agent-management')
        return response

    if include_legacy_teams:
        @router.post('/teams/{rig_id}/seats/{seat_id}/credential')
        def agent_credential(rig_id: str, seat_id: str, request: Request):
            authenticate(request, 'admin', rig_id, human=True)
            team_store = gateway(request).team_platform(rig_id).store
            result = DeviceAccess(control_store(request)).agent_token(rig_id, seat_id, team_store=team_store)
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})

    return router
