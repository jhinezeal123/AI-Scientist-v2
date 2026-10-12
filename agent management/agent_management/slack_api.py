"""Slack settings and explicit human send commands."""
from fastapi import APIRouter, Request
from pydantic import Field

from .api_support import authenticate, control_store, ConflictRoute
from .models import StrictModel
from .slack import SlackIntegration


class SlackConfig(StrictModel):
    enabled: bool
    channel: str | None = Field(default=None, max_length=128)


class SlackMessage(StrictModel):
    text: str = Field(min_length=1, max_length=10000)


def create_slack_router():
    router = APIRouter(prefix='/api/agent-management/integrations/slack', tags=['Slack'], route_class=ConflictRoute)

    def service(request):
        authenticate(request, 'admin', human=True)
        return SlackIntegration(control_store(request))

    @router.get('')
    def slack(request: Request):
        return service(request).slack()

    @router.put('')
    def configure(body: SlackConfig, request: Request):
        return service(request).configure_slack(**body.model_dump())

    @router.post('/messages')
    def send(body: SlackMessage, request: Request):
        return service(request).send_slack(body.text, authorized=True)

    return router
