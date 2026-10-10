"""Scoped team controls in the existing Workbench server."""
from __future__ import annotations

import asyncio
import json
import os
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import Field

from .models import RigSpec, HarnessSpec, TaskRequest, StrictModel, templates
from .remote import DeviceAccess, COOKIE, loopback, remote_surface, transport_guard, digest
from .research_bridge import ResearchCommand
from .resources import CodingResource


def platform(request):
    if not os.environ.get('AI_SCIENTIST_AGENT_CONTROL_TOKEN'):
        raise HTTPException(404, 'Agent management disabled. Set AI_SCIENTIST_AGENT_CONTROL_TOKEN when starting Workbench.')
    gateway = getattr(getattr(request.app.state, 'runtime', None), 'runtime', None)
    if gateway is None or not hasattr(type(gateway), 'platform'):
        raise HTTPException(503, 'Agent gateway is unavailable')
    config = getattr(request.app.state, 'config', None)
    gateway.protected_paths = tuple(p for p in (getattr(config, 'donor_root', None),) if p)
    control = gateway.platform
    control.context.projects = getattr(request.app.state, 'store', None)
    return control


def access(request, scope='read', rig_id=None, *, human=False):
    control = platform(request)
    principal = DeviceAccess(control.store).authenticate(request, scope=scope, rig_id=rig_id, human=human)
    return control, principal


async def remote_boundary(request, call_next):
    # A private HTTPS route must not accidentally expose the unpaired legacy project API.
    if request.url.path!='/health' and remote_surface(request):
        try:
            transport_guard(request)
            path = request.url.path
            if path.startswith('/api/') and path != '/api/agent-management/pair/exchange':
                if not path.startswith('/api/agent-management/'):
                    raise HTTPException(403, 'Remote devices use the scoped multi-agent API')
                access(request)
        except HTTPException as exc:
            return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    return await call_next(request)


class ConflictRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def run(request):
            try:
                return await handler(request)
            except KeyError:
                return JSONResponse({'detail': 'Team, seat or resource not found'}, status_code=404)
            except ValueError as exc:
                return JSONResponse({'detail': str(exc)[:2000]}, status_code=409)
        return run


class CreateTeam(StrictModel):
    id: str = Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')
    spec: RigSpec


class ChangeTeam(StrictModel):
    spec: RigSpec
    revision: int = Field(ge=1)


class Enqueue(StrictModel):
    seat: str
    request_id: str = Field(min_length=1, max_length=128)
    task: TaskRequest
    depends_on: str | None = None


class Message(StrictModel):
    sender: str
    recipient: str = '*'
    body: str = Field(min_length=1, max_length=20000)


class FileBody(StrictModel):
    path: str
    content: str = Field(max_length=1000000)
    sha256: str | None = None


class Pair(StrictModel):
    scopes: list[str] = Field(default_factory=lambda: ['read', 'task', 'message', 'workspace', 'permission'])
    rig_ids: list[str] = Field(min_length=1, max_length=100)


class Exchange(StrictModel):
    pairing_id: str = Field(max_length=64)
    code: str = Field(max_length=256)
    name: str = Field(min_length=1, max_length=120)


class Decision(StrictModel):
    option_id: str = Field(max_length=128)


class Workflow(StrictModel):
    request_id: str = Field(min_length=1, max_length=110)
    instruction: str = Field(min_length=1, max_length=70000)


class ContextBody(StrictModel):
    id: str = Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')
    kind: str
    path: str = Field(max_length=512)
    seats: list[str] = Field(default_factory=list)


class TerminalBody(StrictModel):
    argv: list[str] = Field(min_length=1,max_length=32)
    request_id: str = Field(min_length=1,max_length=128)
    timeout_seconds: int = Field(default=30,ge=1,le=120)


class BundleBody(StrictModel):
    id: str = Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')
    bundle: dict


class SlackConfig(StrictModel):
    enabled: bool
    channel: str | None = Field(default=None,max_length=128)


class SlackMessage(StrictModel):
    text: str = Field(min_length=1,max_length=10000)


def workspace(control, rig_id, seat_id):
    rig = control.store.rig(rig_id)
    seat = next((s for s in rig.seats if s.id == seat_id), None)
    if seat is None:
        raise KeyError(seat_id)
    path, checkpoint = control.workspaces.ensure(rig_id, seat_id, rig.base_ref)
    control.store.seat_workspace(rig_id, seat_id, path, checkpoint)
    return rig, seat, path


def create_team_router():
    router = APIRouter(prefix='/api/agent-management', tags=['Teams'], route_class=ConflictRoute)

    @router.get('/identity')
    def identity(request: Request):
        _, who = access(request)
        cookie=request.cookies.get(COOKIE)
        return {'id': who.id, 'scopes': sorted(who.scopes), 'rig_ids': sorted(who.rig_ids), 'agent': who.agent,
                'csrf':digest(cookie+':csrf') if cookie and not request.headers.get('authorization') else None}

    @router.get('/templates')
    def catalog(request: Request):
        access(request)
        return templates()

    @router.get('/harnesses')
    def harnesses(request: Request, details: bool=False):
        control, who = access(request)
        if details:
            who.require('admin',human=True)
        return [{'spec': s.model_dump() if details else {k:v for k,v in s.model_dump().items() if k not in {'args','executable','managed_home'}},
                 'probe': control.registry.resolve(s.id).probe()} for s in control.store.harnesses()]

    @router.put('/harnesses/{identifier}')
    def configure(identifier: str, body: HarnessSpec, request: Request):
        control, _ = access(request, 'admin', human=True)
        if identifier != body.id:
            raise ValueError('Harness ID mismatch')
        control.store.put_harness(body)
        return body.model_dump()

    @router.post('/harnesses/dsh/import')
    def import_dsh(request: Request):
        control, _ = access(request, 'admin', human=True)
        from .dsh import install_local_profile
        spec = install_local_profile(control.workspaces.repository)
        control.store.put_harness(spec)
        return spec.model_dump()

    @router.get('/teams')
    def teams(request: Request):
        control, who = access(request)
        return [r for r in control.store.rigs() if '*' in who.rig_ids or r['id'] in who.rig_ids]

    @router.post('/teams')
    def create(body: CreateTeam, request: Request):
        control, _ = access(request, 'admin', human=True)
        if body.spec.project_id:
            request.app.state.store.project(body.spec.project_id)
        return control.create(body.id, body.spec)

    @router.get('/teams/{rig_id}')
    def team(rig_id: str, request: Request):
        control, who = access(request, rig_id=rig_id)
        result=control.store.snapshot(rig_id)
        if who.agent:
            for task in result['tasks']:
                if task['seat']!=who.seat_id:
                    task['payload']={}
                    if task['result']:
                        task['result']={k:v for k,v in task['result'].items() if k not in {'files','output'}}
        return result

    @router.get('/teams/{rig_id}/health')
    def health(rig_id: str,request: Request):
        control,_=access(request,rig_id=rig_id)
        team=control.store.snapshot(rig_id)
        with control.lock:
            active=[r['identity'] for key,r in control.active.items() if key[0]==rig_id]
        return {'rig_id':rig_id,'enabled':bool(team['enabled']),'supervised':active,
                'attention':[{'seat_id':s['id'],'state':s['state']} for s in team['seats'] if s['state']=='UNKNOWN'],
                'queue_pending':sum(t['state']=='PENDING' for t in team['tasks'])}

    @router.put('/teams/{rig_id}')
    def topology(rig_id: str, body: ChangeTeam, request: Request):
        control, _ = access(request, 'admin', rig_id, human=True)
        for seat in body.spec.seats:
            control.registry.resolve(seat.harness)
        control.store.update_spec(rig_id, body.spec, body.revision)
        return control.store.snapshot(rig_id)

    @router.post('/teams/{rig_id}/start')
    def start(rig_id: str, request: Request):
        control, _ = access(request, 'task', rig_id, human=True)
        return control.start(rig_id)

    @router.post('/teams/{rig_id}/pause')
    def pause(rig_id: str, request: Request, interrupt: bool = False):
        control, _ = access(request, 'task', rig_id, human=True)
        return control.pause(rig_id, interrupt=interrupt)

    @router.post('/teams/{rig_id}/tasks')
    def enqueue(rig_id: str, body: Enqueue, request: Request):
        control, who = access(request, 'task', rig_id)
        if who.agent and body.seat != who.seat_id:
            raise HTTPException(403, 'Agent can enqueue only for its own seat')
        return control.enqueue(rig_id, body.seat, body.request_id, body.task, depends_on=body.depends_on)

    @router.post('/teams/{rig_id}/workflow')
    def workflow(rig_id: str, body: Workflow, request: Request):
        control, _ = access(request, 'task', rig_id, human=True)
        rig = control.store.rig(rig_id)
        roles = ['lead', 'builder', 'qa', 'reviewer']
        seats = [next((s for s in rig.seats if s.role == role), None) for role in roles]
        if any(s is None for s in seats):
            raise ValueError('Workflow requires Lead, Builder, QA and Reviewer seats')
        tasks, previous = [], None
        for seat in seats:
            task = control.enqueue(rig_id, seat.id, body.request_id + ':' + seat.role,
                TaskRequest(instruction=body.instruction, kind='review' if seat.role in {'qa','reviewer'} else 'coding'), depends_on=previous)
            tasks.append(task)
            previous = task['id']
        return tasks

    @router.delete('/teams/{rig_id}/tasks/{task_id}')
    def cancel(rig_id: str, task_id: str, request: Request):
        control, _ = access(request, 'task', rig_id, human=True)
        control.store.cancel_pending(rig_id, task_id)
        return {'cancelled': task_id}

    @router.post('/teams/{rig_id}/tasks/{task_id}/retry')
    def retry_task(rig_id: str,task_id: str,request: Request):
        control,who=access(request,'task',rig_id,human=True)
        task=next((t for t in control.store.snapshot(rig_id)['tasks'] if t['id']==task_id),None)
        if task is None:
            raise KeyError(task_id)
        if task['payload'].get('kind')=='terminal':
            who.require('workspace',rig_id,human=True)
        result=control.store.retry_stopped(rig_id,task_id)
        if task['payload'].get('kind')=='terminal':
            from .terminal import execute
            protected=[getattr(getattr(request.app.state,'config',None),'donor_root','')]
            return execute(control,rig_id,task['seat'],task['payload']['argv'],request_id=task['request_id'],timeout=task['payload']['timeout_seconds'],protected=[p for p in protected if p])
        return result

    @router.post('/teams/{rig_id}/messages')
    def message(rig_id: str, body: Message, request: Request):
        control, who = access(request, 'message', rig_id)
        if who.agent and body.sender != who.seat_id:
            raise HTTPException(403, 'Agent cannot impersonate another seat')
        identifier=control.store.queue.send(rig_id, body.sender, body.recipient, body.body)
        control.store.publish('message_sent',{'message_id':identifier,'recipient':body.recipient},rig_id=rig_id,seat_id=body.sender)
        return {'id':identifier}

    @router.get('/teams/{rig_id}/messages')
    def messages(rig_id: str, request: Request, after: int = 0):
        control, _ = access(request, rig_id=rig_id)
        return control.store.chatroom(rig_id, after)

    @router.get('/teams/{rig_id}/events')
    def events(rig_id: str, request: Request, after: int = 0):
        control, who = access(request, rig_id=rig_id)
        return control.store.events(rig_id=rig_id, after=after,seat_id=who.seat_id if who.agent else None)

    @router.get('/teams/{rig_id}/stream')
    async def stream(rig_id: str, request: Request, after: int = 0):
        control, who = access(request, rig_id=rig_id)
        cursor = max(after, int(request.headers.get('last-event-id', '0')))
        async def generate():
            nonlocal cursor
            while not await request.is_disconnected():
                # Revocation takes effect on an already-connected stream too.
                try:
                    access(request, rig_id=rig_id)
                except HTTPException:
                    yield 'event: access_revoked\ndata: {}\n\n'
                    break
                rows = await asyncio.to_thread(control.store.events, rig_id=rig_id, after=cursor,seat_id=who.seat_id if who.agent else None)
                for event in rows:
                    cursor = event['id']
                    yield f'id: {cursor}\ndata: {json.dumps(event)}\n\n'
                yield ': heartbeat\n\n'
                await asyncio.sleep(1)
        return StreamingResponse(generate(), media_type='text/event-stream', headers={'Cache-Control':'no-store', 'X-Accel-Buffering':'no'})

    @router.post('/teams/{rig_id}/seats/{seat_id}/interrupt')
    def interrupt(rig_id: str, seat_id: str, request: Request):
        control, _ = access(request, 'task', rig_id, human=True)
        return control.interrupt(rig_id, seat_id)

    @router.post('/teams/{rig_id}/sessions/{session_id}/reconcile')
    def reconcile(rig_id: str, session_id: str, request: Request, retry: bool = False):
        control, _ = access(request, 'task', rig_id, human=True)
        if control.store.session(session_id)['rig_id'] != rig_id:
            raise HTTPException(403, 'Session is outside this team')
        return control.reconcile(session_id, retry=retry)

    @router.get('/teams/{rig_id}/seats/{seat_id}/files')
    def files(rig_id: str, seat_id: str, request: Request):
        control, who = access(request, rig_id=rig_id)
        _, seat, path = workspace(control, rig_id, seat_id)
        if who.agent and who.seat_id!=seat_id:
            raise HTTPException(403,'Agent cannot read another seat workspace')
        result=control.workspaces.files(path)
        return [f for f in result if not who.agent or any(f['path']==p.rstrip('/') or f['path'].startswith(p.rstrip('/')+'/') for p in seat.policy.allowed_paths)]

    @router.get('/teams/{rig_id}/seats/{seat_id}/file')
    def read_file(rig_id: str, seat_id: str, request: Request, path: str):
        control, who = access(request, rig_id=rig_id)
        _, seat, root = workspace(control, rig_id, seat_id)
        if who.agent and (who.seat_id!=seat_id or not any(path==p.rstrip('/') or path.startswith(p.rstrip('/')+'/') for p in seat.policy.allowed_paths)):
            raise HTTPException(403,'File is outside the agent seat scope')
        return control.workspaces.read(root, path)

    @router.put('/teams/{rig_id}/seats/{seat_id}/file')
    def edit_file(rig_id: str, seat_id: str, body: FileBody, request: Request):
        control, _ = access(request, 'workspace', rig_id, human=True)
        with control.lock:
            team = control.store.snapshot(rig_id)
            if any(s['id']==seat_id and s['state'] in {'BUSY','UNKNOWN'} for s in team['seats']):
                raise ValueError('Stop and reconcile the seat before editing')
            _, seat, root = workspace(control, rig_id, seat_id)
            control.workspaces.edit(root, body.path, body.content, body.sha256, seat.policy)
            checkpoint = control.workspaces.checkpoint(root, task_id='manual-' + uuid.uuid4().hex)
            control.store.seat_workspace(rig_id, seat_id, root, checkpoint)
            control.store.publish('file_saved', {'path': body.path, 'checkpoint': checkpoint}, rig_id=rig_id, seat_id=seat_id)
            return control.workspaces.read(root, body.path)

    @router.get('/teams/{rig_id}/seats/{seat_id}/review')
    def review(rig_id: str, seat_id: str, request: Request):
        control, who = access(request, rig_id=rig_id)
        if who.agent and who.seat_id!=seat_id:
            raise HTTPException(403,'Agent cannot review another seat workspace')
        rig, seat, path = workspace(control, rig_id, seat_id)
        return control.workspaces.review(path, rig.base_ref,allowed_paths=seat.policy.allowed_paths if who.agent else None)

    @router.post('/teams/{rig_id}/seats/{seat_id}/terminal')
    def terminal(rig_id: str, seat_id: str, body: TerminalBody, request: Request):
        control, _ = access(request,'workspace',rig_id,human=True)
        from .terminal import execute
        protected=[getattr(getattr(request.app.state,'config',None),'donor_root','')]
        return execute(control,rig_id,seat_id,body.argv,request_id=body.request_id,
            timeout=body.timeout_seconds,protected=[p for p in protected if p])

    @router.post('/teams/{rig_id}/snapshots')
    def snapshot(rig_id: str, request: Request):
        control, _ = access(request, 'workspace', rig_id, human=True)
        return control.snapshot(rig_id)

    @router.get('/teams/{rig_id}/snapshots')
    def snapshots(rig_id: str, request: Request):
        control, _ = access(request, rig_id=rig_id)
        with control.store.connect() as con:
            return [dict(r) for r in con.execute('SELECT id,created_at FROM snapshots WHERE rig_id=? ORDER BY created_at DESC',(rig_id,))]

    @router.post('/teams/{rig_id}/snapshots/{snapshot_id}/restore')
    def restore(rig_id: str, snapshot_id: str, request: Request):
        control, _ = access(request, 'workspace', rig_id, human=True)
        return control.restore(rig_id, snapshot_id)

    @router.get('/worktrees')
    def discover(request: Request):
        control, _ = access(request, 'admin', human=True)
        return control.workspaces.discover()

    @router.post('/teams/{rig_id}/seats/{seat_id}/adopt')
    def adopt(rig_id: str, seat_id: str, request: Request):
        control, _ = access(request, 'workspace', rig_id, human=True)
        return control.adopt(rig_id, seat_id)

    @router.get('/teams/{rig_id}/permissions')
    def permissions(rig_id: str, request: Request):
        control, _ = access(request, rig_id=rig_id)
        return control.permissions.pending(rig_id)

    @router.post('/teams/{rig_id}/context')
    def context(rig_id: str, body: ContextBody, request: Request):
        control, _ = access(request, 'workspace', rig_id, human=True)
        team = control.store.snapshot(rig_id)
        rig = RigSpec.model_validate(team['spec'])
        source = (control.context.library_reference(rig, body.id, body.path, body.seats) if body.kind=='library'
            else control.context.register(body.id, body.kind, body.path, body.seats))
        spec = RigSpec.model_validate({**team['spec'], 'context':[c for c in team['spec']['context'] if c['id']!=body.id]+[source.model_dump()]})
        control.store.update_spec(rig_id, spec, team['revision'])
        return source.model_dump()

    @router.get('/teams/{rig_id}/context/{seat_id}')
    def context_pack(rig_id: str, seat_id: str, request: Request):
        control, who = access(request, rig_id=rig_id)
        if who.agent and who.seat_id!=seat_id:
            raise HTTPException(403,'Context is routed to another seat')
        rig=control.store.rig(rig_id)
        if seat_id not in {s.id for s in rig.seats}:
            raise KeyError(seat_id)
        return control.context.pack(rig, seat_id)

    @router.get('/teams/{rig_id}/bundle')
    def bundle_export(rig_id: str, request: Request):
        control,_=access(request,rig_id=rig_id)
        from .bundles import export_bundle
        return export_bundle(control,rig_id)

    @router.post('/bundles')
    def bundle_import(body: BundleBody, request: Request):
        control,_=access(request,'admin',human=True)
        from .bundles import import_bundle
        if body.bundle.get('payload',{}).get('spec',{}).get('project_id'):
            request.app.state.store.project(body.bundle['payload']['spec']['project_id'])
        return import_bundle(control,body.id,body.bundle)

    @router.get('/teams/{rig_id}/telemetry')
    def usage(rig_id: str, request: Request):
        control,_=access(request,rig_id=rig_id)
        from .resources import telemetry
        return telemetry(control,rig_id)

    @router.get('/teams/{rig_id}/resources')
    def resources(rig_id: str,request: Request):
        control,_=access(request,rig_id=rig_id)
        from .resources import resource_limits
        return [r.model_dump() for r in resource_limits(control.store,rig_id)]

    @router.put('/teams/{rig_id}/resources/{identifier}')
    def resource(rig_id: str,identifier: str,body: CodingResource,request: Request):
        control,_=access(request,'workspace',rig_id,human=True)
        if body.id!=identifier:
            raise ValueError('Resource ID mismatch')
        from .resources import configure_resource
        return configure_resource(control.store,rig_id,body)

    @router.delete('/teams/{rig_id}/resources/{identifier}')
    def delete_resource(rig_id: str,identifier: str,request: Request):
        control,_=access(request,'workspace',rig_id,human=True)
        from .resources import remove_resource
        remove_resource(control.store,rig_id,identifier)
        return {'removed':identifier}

    def bridge(request,rig_id,*,mutation=False):
        control,_=access(request,'research' if mutation else 'read',rig_id,human=True)
        from .research_bridge import ResearchBridge
        return ResearchBridge(control,request.app.state.store,request.app.state.working)

    @router.get('/teams/{rig_id}/research/binding/{run_id}')
    def research_binding(rig_id: str,run_id: str,request: Request):
        return bridge(request,rig_id).binding(rig_id,run_id)

    @router.post('/teams/{rig_id}/research')
    async def research_dispatch(rig_id: str,body: ResearchCommand,request: Request):
        return await bridge(request,rig_id,mutation=True).dispatch(rig_id,body)

    @router.get('/teams/{rig_id}/research')
    def research_commands(rig_id: str,request: Request):
        return bridge(request,rig_id).commands(rig_id)

    @router.post('/teams/{rig_id}/research/{request_id}/reconcile')
    async def research_reconcile(rig_id: str,request_id: str,request: Request,retry: bool=False):
        return await bridge(request,rig_id,mutation=True).reconcile(rig_id,request_id,retry=retry)

    @router.post('/teams/{rig_id}/seats/{seat_id}/credential')
    def agent_credential(rig_id: str,seat_id: str,request: Request):
        control,_=access(request,'admin',rig_id,human=True)
        from .remote import DeviceAccess
        return JSONResponse(DeviceAccess(control.store).agent_token(rig_id,seat_id),headers={'Cache-Control':'no-store'})

    @router.get('/integrations/slack')
    def slack(request: Request):
        control,_=access(request,'admin',human=True)
        from .resources import Integrations
        return Integrations(control.store).slack()

    @router.put('/integrations/slack')
    def slack_config(body: SlackConfig,request: Request):
        control,_=access(request,'admin',human=True)
        from .resources import Integrations
        return Integrations(control.store).configure_slack(**body.model_dump())

    @router.post('/integrations/slack/messages')
    def slack_send(body: SlackMessage,request: Request):
        control,_=access(request,'admin',human=True)
        from .resources import Integrations
        return Integrations(control.store).send_slack(body.text,authorized=True)

    @router.post('/teams/{rig_id}/permissions/{permission_id}')
    def decide(rig_id: str, permission_id: str, body: Decision, request: Request):
        control, _ = access(request, 'permission', rig_id, human=True)
        if permission_id not in {r['id'] for r in control.permissions.pending(rig_id)}:
            raise KeyError(permission_id)
        return control.permissions.decide(permission_id, body.option_id)

    @router.post('/pair')
    def pair(body: Pair, request: Request):
        control, _ = access(request, 'admin', human=True)
        for rig_id in body.rig_ids:
            if rig_id != '*':
                control.store.rig(rig_id)
        return DeviceAccess(control.store).pairing(scopes=body.scopes, rig_ids=body.rig_ids)

    @router.post('/pair/exchange')
    def exchange(body: Exchange, request: Request):
        transport_guard(request)
        result = DeviceAccess(platform(request).store).exchange(body.pairing_id, body.code, body.name)
        response = JSONResponse({k:v for k,v in result.items() if k != 'token'})
        response.set_cookie(COOKIE, result['token'], max_age=30*86400, httponly=True,
            secure=request.url.scheme=='https', samesite='strict', path='/api/agent-management')
        response.headers['Cache-Control'] = 'no-store'
        return response

    @router.get('/devices')
    def devices(request: Request):
        control, _ = access(request, 'admin', human=True)
        return DeviceAccess(control.store).devices()

    @router.post('/logout')
    def logout(request: Request):
        control,who=access(request,human=True)
        if who.id!='local-operator':
            DeviceAccess(control.store).revoke(who.id)
        response=JSONResponse({'signed_out':True},headers={'Cache-Control':'no-store'})
        response.delete_cookie(COOKIE,path='/api/agent-management')
        return response

    @router.delete('/devices/{device_id}')
    def revoke(device_id: str, request: Request):
        control, _ = access(request, 'admin', human=True)
        DeviceAccess(control.store).revoke(device_id)
        return {'revoked': device_id}

    return router
