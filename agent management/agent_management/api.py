"""Compose provider configuration and the existing management endpoints."""
from fastapi import APIRouter
from .auth_api import create_auth_router
from .preset_api import create_preset_router
from .team_api import create_team_router

def create_management_router():
    router = APIRouter()
    for factory in (create_auth_router, create_preset_router, create_team_router):
        router.include_router(factory())
    return router
