"""Application composition: feature routers keep their own policy and state."""
from fastapi import APIRouter

from .auth_api import create_auth_router
from .preset_api import create_preset_router, preset_service
from .remote_api import create_remote_router
from .slack_api import create_slack_router


def create_management_router(*, include_legacy_teams=False):
    router = APIRouter()
    router.include_router(create_auth_router(include_legacy_teams=include_legacy_teams))
    for factory in (create_preset_router, create_remote_router, create_slack_router):
        router.include_router(factory())
    if include_legacy_teams:
        from .team_api import create_team_router
        from .project_team_api import create_project_team_router
        router.include_router(create_team_router())
        router.include_router(create_project_team_router(lambda request: preset_service(request).list()[0]))
    return router
