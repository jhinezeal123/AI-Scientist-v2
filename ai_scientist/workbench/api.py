"""Library, approval, implementation and durable MCP submission endpoints."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, field_validator

from .models import StrictModel
from .resources import readiness_sources
from .store import StoreConflict


class ProjectInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class ResourceInput(StrictModel):
    kind: Literal["text", "url", "dataset"]
    title: str = Field(min_length=1, max_length=240)
    url: str | None = Field(default=None, max_length=2000)
    content: str = Field(default="", max_length=60_000)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        if value:
            from urllib.parse import urlsplit
            parsed = urlsplit(value)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Source URL must be HTTP(S) without credentials")
        return value


class ResourceUpdate(ResourceInput):
    expected_version: int = Field(ge=1)


class IdeaInput(StrictModel):
    text: str = Field(min_length=1, max_length=20_000)


class ContextInput(StrictModel):
    idea_id: str
    resource_ids: list[str] = Field(min_length=1, max_length=30)


class IdeaUpdate(IdeaInput):
    expected_text: str = Field(max_length=20_000)


class AnswerInput(StrictModel):
    proposal_id: str
    version: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=20_000)


class ApprovalInput(StrictModel):
    version: int = Field(ge=1)
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def library_router(store, workspace_root):
    router = APIRouter(prefix="/api")

    def call(operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from exc
        except StoreConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(422, str(exc)) from exc

    async def async_call(operation, *args):
        try:
            return await operation(*args)
        except KeyError as exc:
            raise HTTPException(404, str(exc.args[0])) from exc
        except StoreConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (RuntimeError, TimeoutError) as exc:
            raise HTTPException(503, 'MCP readiness unavailable; no new push authorized') from exc

    @router.get("/projects")
    def projects():
        return call(store.list_projects)

    @router.post("/projects", status_code=201)
    def create_project(body: ProjectInput):
        if not body.name.strip():
            raise HTTPException(422, "Project name must contain text")
        return call(store.create_project, body.name)

    @router.get("/projects/{project_id}/resources")
    def resources(project_id: str):
        return call(store.resources, project_id)

    @router.post("/projects/{project_id}/resources", status_code=201)
    def add_resource(project_id: str, body: ResourceInput):
        return call(store.save_resource, project_id, body.model_dump())

    @router.put("/projects/{project_id}/resources/{resource_id}")
    def update_resource(project_id: str, resource_id: str, body: ResourceUpdate):
        return call(store.save_resource, project_id, body.model_dump(exclude={"expected_version"}),
                    resource_id, body.expected_version)

    @router.post("/projects/{project_id}/import-readiness")
    def import_readiness(project_id: str):
        call(store.project, project_id)
        sources = call(readiness_sources, workspace_root)
        existing = call(store.resources, project_id)
        imported = []
        for source in sources:
            # Repeated click is idempotent for an unchanged imported source.
            match = next((item for item in existing if all(item[key] == source[key]
                         for key in ("kind", "title", "url", "content"))), None)
            imported.append(match or call(store.save_resource, project_id, source))
        return imported

    @router.get("/projects/{project_id}/ideas")
    def ideas(project_id: str):
        return call(store.ideas, project_id)

    @router.post("/projects/{project_id}/ideas", status_code=201)
    def add_idea(project_id: str, body: IdeaInput):
        return call(store.save_idea, project_id, body.text)

    @router.put("/projects/{project_id}/ideas/{idea_id}")
    def update_idea(project_id: str, idea_id: str, body: IdeaUpdate):
        return call(store.update_idea, project_id, idea_id, body.text, body.expected_text)

    @router.post("/projects/{project_id}/plan", status_code=202)
    async def plan(project_id: str, body: ContextInput, request: Request):
        return await async_call(request.app.state.service.start, project_id, body.idea_id, body.resource_ids)

    @router.post("/projects/{project_id}/ideas/{idea_id}/answer")
    async def answer(project_id: str, idea_id: str, body: AnswerInput, request: Request):
        return await async_call(request.app.state.service.answer, project_id, idea_id, body.proposal_id, body.version, body.text)

    @router.get("/projects/{project_id}/proposals")
    def proposals(project_id: str, idea_id: str | None = None):
        return call(store.proposals, project_id, idea_id)

    @router.post("/projects/{project_id}/proposals/{proposal_id}/approve")
    async def approve(project_id: str, proposal_id: str, body: ApprovalInput, request: Request):
        return await async_call(request.app.state.service.approve, project_id, proposal_id, body.version, body.context_sha256)

    @router.post("/projects/{project_id}/context")
    def context(project_id: str, body: ContextInput):
        return call(store.context_snapshot, project_id, body.idea_id, body.resource_ids)

    @router.get("/projects/{project_id}/history")
    def history(project_id: str, request: Request):
        return call(store.history, project_id)

    @router.post('/projects/{project_id}/runs/{run_id}/implement', status_code=202)
    async def implement(project_id: str, run_id: str, request: Request):
        return await async_call(request.app.state.implementation.start, project_id, run_id)

    @router.get('/projects/{project_id}/runs/{run_id}')
    def run_detail(project_id: str, run_id: str, request: Request):
        return call(request.app.state.implementation.detail, project_id, run_id)


    @router.get('/projects/{project_id}/runs/{run_id}/artifacts/{name:path}')
    def artifact(project_id: str, run_id: str, name: str, request: Request):
        from fastapi.responses import FileResponse
        detail = call(request.app.state.implementation.detail, project_id, run_id)
        if name not in detail['artifacts']:
            raise HTTPException(404, 'Artifact not found')
        root = call(request.app.state.implementation.root, project_id, run_id)
        path = root / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise HTTPException(404, 'Artifact not found')
        return FileResponse(path, filename=path.name)

    return router
