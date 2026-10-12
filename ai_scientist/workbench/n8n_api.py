"""Human project controls and a loopback n8n bridge with separate authority."""
import hmac
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from .models import StrictModel
from .workflow_models import WorkflowSpec
from .runtime import _agent_gateway_class


class WorkflowInput(StrictModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    spec: WorkflowSpec


class HumanAnswer(StrictModel):
    result: dict


class LiteratureKey(StrictModel):
    api_key: str = Field(min_length=1,max_length=2000)


class StepInput(StrictModel):
    project_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    workflow_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    generation: int = Field(ge=1)
    iteration: int = Field(ge=0, le=100)
    step: str = Field(max_length=32)
    execution_id: str = Field(default='', max_length=64)
    resume_url: str = Field(default='', max_length=2048)
    proposal_round: int = Field(default=0, ge=0, le=1000)


class TurnInput(StrictModel):
    execution_id: str = Field(default='', max_length=64)


def create_n8n_router():
    _agent_gateway_class()
    from _ai_scientist_agent_management.api_support import authenticate, ConflictRoute
    from _ai_scientist_agent_management.auth import loopback, remote_surface
    router = APIRouter(prefix='/api/agent-management', tags=['Project workflows'], route_class=ConflictRoute)

    def owner(request, project=None, scope='read'):
        authenticate(request, scope, project, human=True)
        return request.app.state.research_workflows

    def bridge(request):
        service = request.app.state.research_workflows
        if not loopback(request) or remote_surface(request) or request.headers.get('origin'):
            raise HTTPException(403, 'n8n bridge is local only')
        if not hmac.compare_digest(request.headers.get('x-workbench-n8n', ''), service.client.token):
            raise HTTPException(401, 'n8n bridge credential required')
        return service

    @router.get('/workflow-projects')
    def projects(request: Request):
        service = owner(request)
        who = authenticate(request, human=True)
        return [p for p in service.projects.list_projects() if '*' in who.rig_ids or p['id'] in who.rig_ids]

    @router.get('/n8n/status')
    def status(request: Request):
        return owner(request).client.status()

    @router.post('/n8n/start')
    def start_n8n(request: Request):
        service = owner(request, scope='admin')
        return service.client.start(service.projects.workspace)

    @router.post('/literature/key')
    def literature_key(body: LiteratureKey, request: Request):
        service = owner(request,scope='admin')
        from .research_literature import save_search_key
        save_search_key(service.projects.workspace,body.api_key)
        return {'configured':True}

    @router.get('/projects/{project}/workflow-options')
    def options(project: str, request: Request):
        service = owner(request, project)
        service.projects.project(project)
        from .benchmarks import BenchmarkCatalog
        from .research_literature import saved_search_key
        return {'project_id': project, 'resources': service.projects.resources(project),
                'benchmarks': BenchmarkCatalog(service.projects).list(project),
                'accounts': service.working.accounts.list() if service.working.accounts else [],
                'n8n': service.client.status(), 'literature':{'configured':bool(saved_search_key(service.projects.workspace))}}

    @router.get('/projects/{project}/workflows')
    def workflows(project: str, request: Request):
        return owner(request, project).list(project)

    @router.post('/projects/{project}/workflows')
    def create(project: str, body: WorkflowInput, request: Request):
        return owner(request, project, 'research').create(project, body.request_id, body.spec)

    @router.get('/projects/{project}/workflows/{identity}')
    def detail(project: str, identity: str, request: Request):
        return owner(request, project).view(project, identity)

    @router.post('/projects/{project}/workflows/{identity}/start')
    async def start(project: str, identity: str, request: Request):
        return await owner(request, project, 'research').start(project, identity)

    @router.post('/projects/{project}/workflows/{identity}/pause')
    async def pause(project: str, identity: str, request: Request):
        return await owner(request, project, 'research').pause(project, identity)

    @router.post('/projects/{project}/workflows/{identity}/reconcile')
    async def reconcile(project: str, identity: str, request: Request):
        return await owner(request, project, 'research').reconcile(project, identity)

    @router.post('/projects/{project}/workflows/{identity}/inputs/{input_id}')
    def answer(project: str, identity: str, input_id: str, body: HumanAnswer, request: Request):
        service = owner(request, project, 'research')
        service.current(project, identity)
        service.store.answer(project, identity, input_id, body.result)
        return service.view(project, identity)

    @router.post('/n8n/step')
    async def step(body: StepInput, request: Request):
        return await bridge(request).step(body.project_id, body.workflow_id, body.generation,
                                         body.iteration, body.step, body.execution_id, body.resume_url, body.proposal_round)

    @router.post('/projects/{project}/workflows/{identity}/callbacks/retry')
    async def retry_callbacks(project: str, identity: str, request: Request):
        service = owner(request, project, 'research')
        service.current(project, identity)
        service.callbacks.retry(project, identity)
        return service.view(project, identity)

    @router.post('/n8n/tickets/{ticket}/turn')
    async def turn(ticket: str, body: TurnInput, request: Request):
        return await bridge(request).agent_turns.turn(ticket, body.execution_id)

    @router.post('/n8n/tickets/{ticket}/action/{turn}')
    async def action(ticket: str, turn: int, request: Request):
        return await bridge(request).agent_turns.action(ticket, turn)

    return router
