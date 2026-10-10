"""The same personal-device scopes guard stage configuration and delegation."""
from fastapi import APIRouter, Request
from pydantic import Field
from .models import StrictModel
from .workflow_models import WorkflowSpec
from .runtime import _agent_gateway_class

class WorkflowInput(StrictModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    spec: WorkflowSpec

class HumanAnswer(StrictModel):
    result: dict

def create_workflow_router():
    _agent_gateway_class()
    from _ai_scientist_agent_management.team_api import access, ConflictRoute
    router = APIRouter(prefix='/api/agent-management', tags=['Research workflows'], route_class=ConflictRoute)

    def service(request, rig, scope='read'):
        access(request, scope, rig, human=True)
        return request.app.state.research_workflows

    @router.get('/workflow-projects')
    def projects(request: Request):
        access(request, 'admin', human=True)
        return request.app.state.store.list_projects()

    @router.get('/teams/{rig}/workflow-options')
    def options(rig: str, request: Request):
        owner = service(request, rig)
        project = owner.project(rig)
        from .benchmarks import BenchmarkCatalog
        return {'project_id': project, 'resources': owner.projects.resources(project),
                'benchmarks': BenchmarkCatalog(owner.projects).list(project),
                'accounts': owner.working.accounts.list() if owner.working.accounts else []}

    @router.get('/teams/{rig}/workflows')
    def workflows(rig: str, request: Request):
        owner = service(request, rig)
        return owner.store.list(owner.project(rig), rig)

    @router.post('/teams/{rig}/workflows')
    def create(rig: str, body: WorkflowInput, request: Request):
        owner = service(request, rig, 'research')
        return owner.create(rig, body.request_id, body.spec)

    @router.get('/teams/{rig}/workflows/{identity}')
    def detail(rig: str, identity: str, request: Request):
        return service(request, rig).view(rig, identity)

    @router.post('/teams/{rig}/workflows/{identity}/start')
    async def start(rig: str, identity: str, request: Request):
        return await service(request, rig, 'research').start(rig, identity)

    @router.post('/teams/{rig}/workflows/{identity}/pause')
    async def pause(rig: str, identity: str, request: Request):
        return await service(request, rig, 'research').pause(rig, identity)

    @router.post('/teams/{rig}/workflows/{identity}/reconcile')
    async def reconcile(rig: str, identity: str, request: Request):
        return await service(request, rig, 'research').reconcile(rig, identity)

    @router.post('/teams/{rig}/workflows/{identity}/inputs/{input_id}')
    def answer(rig: str, identity: str, input_id: str, body: HumanAnswer, request: Request):
        owner = service(request, rig, 'research')
        row = owner.view(rig, identity)
        owner.store.answer(row['project_id'], identity, input_id, body.result)
        return owner.view(rig, identity)

    return router
