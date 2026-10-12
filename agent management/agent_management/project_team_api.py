"""Composition boundary between reusable presets and Project-owned teams."""
from fastapi import APIRouter, Request

from .api_support import authenticate, gateway, ConflictRoute
from .project_teams import ProjectTeams, default_team


def create_project_team_router(default_pair):
    """default_pair(request) supplies value data; team policy does not know presets."""
    router = APIRouter(prefix='/api/agent-management', tags=['Project teams'], route_class=ConflictRoute)

    @router.get('/templates')
    def templates(request: Request):
        authenticate(request)
        return [default_team({'id': None, 'name': 'Mặc định'}, default_pair(request)).model_dump()]

    @router.get('/projects/{project_id}/team')
    def project_team(project_id: str, request: Request):
        authenticate(request, 'admin', human=True)
        return ProjectTeams(gateway(request)).get(project_id)

    @router.post('/projects/{project_id}/team')
    def setup(project_id: str, request: Request):
        authenticate(request, 'admin', human=True)
        owner = ProjectTeams(gateway(request))
        existing = owner.get(project_id)
        return existing if existing else owner.setup(project_id, default_pair(request))

    return router
