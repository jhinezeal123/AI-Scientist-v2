"""Drive configurable stage actors through existing project and research services."""
import asyncio
import json
import uuid
from .agents.contracts import RuntimeCancelled, RuntimeUncertain
from .models import WorkingProposal
from .stage_runtime import StageRuntime
from .store import StoreConflict
from .worker import RuntimeWorker
from .workflow_models import STAGES, WorkflowSpec
from .workflow_store import WorkflowStore

IDEA_SCHEMA = {'type': 'object', 'required': ['title', 'text'], 'properties': {
    'title': {'type': 'string', 'minLength': 1, 'maxLength': 80},
    'text': {'type': 'string', 'minLength': 1, 'maxLength': 20000}}, 'additionalProperties': False}
APPROVAL_SCHEMA = {'type': 'object', 'required': ['approve', 'reason'], 'properties': {
    'approve': {'type': 'boolean'}, 'reason': {'type': 'string', 'minLength': 1}}, 'additionalProperties': False}

from .research_steps import ResearchSteps

class ResearchWorkflows:
    check_budget = staticmethod(ResearchSteps.check_budget)
    def __init__(self, planner, working, gateway):
        self.planner, self.working, self.gateway = planner, working, gateway
        self.projects = planner.store
        self.store = WorkflowStore(self.projects)
        self.tasks, self.workers = {}, {}
        self.locks = {}
        self.closed = False
        self.steps = ResearchSteps(self)

    def control(self, rig_id):
        resolve = getattr(self.gateway, 'team_platform', None)
        return resolve(rig_id) if resolve else self.gateway.platform

    def project(self, rig_id):
        project = self.control(rig_id).store.rig(rig_id).project_id
        if not project:
            raise ValueError('Bind this research team to a project first')
        self.projects.project(project)
        return project

    def create(self, rig_id, identity, spec):
        project = self.project(rig_id)
        rig = self.control(rig_id).store.rig(rig_id)
        if any(v.seat not in {s.id for s in rig.seats} for stage,v in spec.stages.items()
               if stage not in {'literature','citations','vision'} or stage in spec.active_stages()):
            raise ValueError('Stage actor references a seat outside this team')
        if spec.benchmark_id:
            from .benchmarks import BenchmarkCatalog
            BenchmarkCatalog(self.projects).require(project, spec.benchmark_id)
        if self.working.accounts:
            self.working.accounts.require(spec.account)
        resources = self.projects.resources(project)
        known = {v['id'] for v in resources}
        if set(spec.resource_ids) - known:
            raise ValueError('Context is outside the selected project')
        from .store import canonical, digest
        fingerprints = {v['id']:digest(canonical(v)) for v in resources if v['id'] in spec.resource_ids}
        return self.store.create(project, rig_id, identity, spec, fingerprints)

    def runtime_for_run(self, key):
        project, run = key
        # A run is bound in the authoritative workflow before Working admission.
        with self.projects.connection(project) as con:
            exists = con.execute("SELECT 1 FROM sqlite_master WHERE name='research_workflows'").fetchone()
            rows = con.execute('SELECT id,state_json FROM research_workflows').fetchall() if exists else []
        for row in rows:
            state = json.loads(row['state_json'])
            if state.get('run_id') == run or run in state['runs']:
                return StageRuntime(self, project, row['id'])
        return self.planner.worker.runtime

    def view(self, rig, identity):
        project = self.project(rig)
        row = self.store.get(project, identity)
        if row['rig_id'] != rig:
            raise ValueError('Workflow belongs to another team')
        row['inputs'] = self.store.inputs(project, identity)
        row['project_id'] = project
        if row['state'].get('run_id'):
            row['run'] = self.working.detail(project, row['state']['run_id'])
        return row

    async def start(self, rig, identity):
        async with self.locks.setdefault(rig,asyncio.Lock()):
            return await self._start(rig,identity)

    async def _start(self, rig, identity):
        row = self.view(rig, identity)
        if identity in self.tasks and not self.tasks[identity].done():
            return row
        if row['state']['status'] in {'DONE', 'UNKNOWN'}:
            raise StoreConflict('Completed/uncertain workflow cannot be replayed')
        if any(other['id'] != identity and other['state']['status'] in {'RUNNING','WAITING','UNKNOWN'}
               for other in self.store.list(row['project_id'], rig)):
            raise StoreConflict('Stop or reconcile the current project workflow before starting another')
        await asyncio.to_thread(self.preflight,rig,WorkflowSpec.model_validate(row['spec']))
        if row['state'].get('run_id'):
            # Existing runs can be observed, never admitted again.
            record = self.working.record(row['project_id'], row['state']['run_id'])
            if record and not record.get('stop_confirmed') and row['state']['status'] == 'PAUSED':
                raise StoreConflict('Reconcile the existing Working run before resuming')
        self.store.change(row['project_id'], identity, lambda s: s.update(status='RUNNING', error=None,generation=s.get('generation',0)+1))
        self.control(rig).start(rig)
        self.tasks[identity] = asyncio.create_task(self.drive(row['project_id'], identity))
        return self.view(rig, identity)

    def preflight(self, rig_id, spec):
        platform = self.control(rig_id)
        rig = platform.store.rig(rig_id)
        checked = set()
        for stage in spec.active_stages():
            binding = spec.stages[stage]
            if binding.actor!='agent':
                continue
            seat = next(s for s in rig.seats if s.id==binding.seat)
            if seat.harness not in checked:
                probe = platform.registry.resolve(seat.harness).probe()
                if not probe.get('ready'):
                    raise StoreConflict(f'Harness {seat.harness} for {stage} is not ready; configure it before starting')
                checked.add(seat.harness)

    async def pause(self, rig, identity):
        async with self.locks.setdefault(rig,asyncio.Lock()):
            return await self._pause(rig,identity)

    async def _pause(self, rig, identity):
        row = self.view(rig, identity)
        self.store.change(row['project_id'], identity, lambda s: s.update(status='PAUSED',generation=s.get('generation',0)+1))
        task = self.tasks.get(identity)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
        worker = self.workers.get(identity)
        if worker:
            await worker.close(5)
            if worker.state.get('status')=='unknown':
                owned = {e.get('task_id') for e in row['state']['events']}
                unresolved = any(t['id'] in owned and t['state'] in {'PENDING','LEASED','UNKNOWN'}
                                 for t in self.control(rig).store.snapshot(rig)['tasks'])
                if not unresolved and (worker.future is None or worker.future.done()):
                    # Caller cancellation can finish after a human-wait thread has
                    # already exited. Terminal owned tasks prove no provider remains.
                    worker.acknowledge_stopped()
                else:
                    self.store.change(row['project_id'],identity,lambda s:s.update(status='UNKNOWN',error='Planner process stop is uncertain; reconcile before resuming'))
        run = row['state'].get('run_id')
        if run and self.working.record(row['project_id'], run):
            await self.working.stop(row['project_id'], run)
        control = self.control(rig)
        if hasattr(control, 'pause'):
            control.pause(rig, interrupt=True)
        return self.view(rig, identity)

    async def drive(self, project, identity):
        runtime = StageRuntime(self, project, identity)
        spec = runtime.spec
        try:
            while True:
                runtime.check()
                state = self.store.get(project, identity)['state']
                from .store import canonical, digest
                selected = {v['id']:digest(canonical(v)) for v in self.projects.resources(project) if v['id'] in spec.resource_ids}
                if selected != state.get('source_fingerprints',{}):
                    raise StoreConflict('Selected Library sources changed; create a new workflow grant')
                if state['iteration'] >= spec.max_runs:
                    self.store.change(project, identity, lambda s: s.update(status='DONE', stage='review'))
                    return
                await self.steps.prepare_idea(runtime)
                await self.steps.prepare_proposal(runtime)
                await self.steps.approve_proposal(runtime)
                await self.steps.execute_run(runtime)
                await self.steps.collect_run(runtime)
        except (RuntimeCancelled, asyncio.CancelledError):
            self.store.change(project, identity, lambda s: s.update(status='PAUSED') if s.get('generation',0)==runtime.generation else None)
        except RuntimeUncertain:
            self.store.change(project, identity, lambda s: s.update(status='UNKNOWN', error='Reconcile the uncertain stage before continuing'))
        except Exception as exc:
            self.store.change(project, identity, lambda s: s.update(status='PAUSED', error=str(exc)[:1000]))
        finally:
            control = self.control(runtime.row['rig_id'])
            if hasattr(control, 'pause'):
                control.pause(runtime.row['rig_id'], interrupt=True)

    async def close(self):
        self.closed = True
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        for worker in self.workers.values():
            await worker.close(5)

    async def reconcile(self, rig, identity):
        row = self.view(rig, identity)
        tasks = self.control(rig).store.snapshot(rig)['tasks']
        owned = {e.get('task_id') for e in row['state']['events']}
        if any(t['id'] in owned and t['state'] in {'LEASED','UNKNOWN'} for t in tasks):
            raise StoreConflict('Reconcile the owned coding session first in Tasks & sessions')
        run = row['state'].get('run_id')
        if run and self.working.record(row['project_id'],run):
            await self.working.reconcile(row['project_id'],run)
            if not self.working.record(row['project_id'],run).get('stop_confirmed'):
                raise StoreConflict('Kaggle session stop is still uncertain')
        state_path = self.projects.directory(row['project_id'])/'automation'/identity/'planner-state.json'
        if state_path.exists():
            worker = self.workers.get(identity) or RuntimeWorker(StageRuntime(self,row['project_id'],identity),state_path,uncertain_error=RuntimeUncertain)
            if worker.future is not None and not worker.future.done():
                raise StoreConflict('Planner runtime thread is still active')
            await worker.close(5)
            worker.acknowledge_stopped()
            self.workers[identity] = worker
        self.store.change(row['project_id'],identity,lambda s:s.update(status='PAUSED',error=None))
        return self.view(rig,identity)

    def recover(self):
        for project in self.projects.list_projects():
            with self.projects.connection(project['id']) as con:
                if not con.execute("SELECT 1 FROM sqlite_master WHERE name='research_workflows'").fetchone():
                    continue
                rows = con.execute('SELECT id,state_json FROM research_workflows').fetchall()
            for row in rows:
                state = json.loads(row['state_json'])
                if state['status'] in {'RUNNING', 'WAITING'}:
                    self.store.change(project['id'], row['id'], lambda s: s.update(status='PAUSED', error='Backend restarted; review existing tasks/run before resuming'))
