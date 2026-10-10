"""Opt-in local control API through the *existing* FastAPI application.

No execution/approval endpoints are exposed here. An explicit environment token
is required even on loopback; deploy through a secured tunnel, not bare 0.0.0.0.
"""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RigBody(StrictBody):
    rig_id: str = Field(min_length=1, max_length=64)
    seats: list[str] = Field(min_length=1, max_length=32)


class TaskBody(StrictBody):
    seat: str
    request_id: str = Field(min_length=1, max_length=128)
    task: dict
    depends_on: str | None = None


class MessageBody(StrictBody):
    sender: str
    recipient: str
    body: str = Field(min_length=1, max_length=20_000)


def create_router():
    router = APIRouter(prefix="/api/agent-management", tags=["Agent management"])

    def gateway(request: Request):
        secret = os.environ.get("AI_SCIENTIST_AGENT_CONTROL_TOKEN", "")
        if not secret:
            raise HTTPException(404, "Agent management API disabled")
        auth = request.headers.get("Authorization", "")
        if not hmac.compare_digest(auth, "Bearer " + secret):
            raise HTTPException(401, "Not authorized")
        runtime = getattr(getattr(request.app.state, "runtime", None), "runtime", None)
        if runtime is None or not hasattr(runtime, "create_rig"):
            raise HTTPException(503, "Agent management gateway unavailable")
        return runtime

    @router.get("/providers")
    def providers(request: Request):
        return gateway(request).capabilities()

    @router.post("/rigs")
    def create_rig(body: RigBody, request: Request):
        try:
            return gateway(request).create_rig(body.rig_id, seats=body.seats)
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from None

    @router.get("/rigs/{rig_id}")
    def rig(rig_id: str, request: Request):
        try:
            return gateway(request).snapshot(rig_id)
        except KeyError:
            raise HTTPException(404, "Rig not found") from None

    @router.post("/rigs/{rig_id}/tasks")
    def enqueue(rig_id: str, body: TaskBody, request: Request):
        try:
            return gateway(request).enqueue(
                rig_id, body.seat, body.request_id, body.task,
                depends_on=body.depends_on)
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from None

    @router.post("/rigs/{rig_id}/messages")
    def send_message(rig_id: str, body: MessageBody, request: Request):
        try:
            return {"message_id": gateway(request).send(
                rig_id, body.sender, body.recipient, body.body)}
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from None

    @router.get("/rigs/{rig_id}/seats/{seat}/inbox")
    def inbox(rig_id: str, seat: str, request: Request, after: int = 0):
        try:
            return gateway(request).inbox(rig_id, seat, after=after)
        except (KeyError, ValueError) as exc:
            raise HTTPException(404, str(exc)) from None

    return router
