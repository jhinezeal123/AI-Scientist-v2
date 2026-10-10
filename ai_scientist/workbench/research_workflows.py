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

class ResearchWorkflows:
    def __init__(self, planner, working, gateway):
        self.planner, self.working, self.gateway = planner, working, gateway
        self.projects = planner.store
        self.store = WorkflowStore(self.projects)
        self.tasks, self.workers = {}, {}
        self.locks = {}
        self.closed = False

    def project(self, rig_id):
        project = self.gateway.platform.store.rig(rig_id).project_id
        if not project:
            raise ValueError('Bind this research team to a project first')
        self.projects.project(project)
        return project

    def create(self, rig_id, identity, spec):
        project = self.project(rig_id)
        rig = self.gateway.platform.store.rig(rig_id)
        if any(v.seat not in {s.id for s in rig.seats} for v in spec.stages.values()):
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
        async with self.locks.setdefault(identity,asyncio.Lock()):
            return await self._start(rig,identity)

    async def _start(self, rig, identity):
        row = self.view(rig, identity)
        if identity in self.tasks and not self.tasks[identity].done():
            return row
        if row['state']['status'] in {'DONE', 'UNKNOWN'}:
            raise StoreConflict('Completed/uncertain workflow cannot be replayed')
        await asyncio.to_thread(self.preflight,rig,WorkflowSpec.model_validate(row['spec']))
        if row['state'].get('run_id'):
            # Existing runs can be observed, never admitted again.
            record = self.working.record(row['project_id'], row['state']['run_id'])
            if record and not record.get('stop_confirmed') and row['state']['status'] == 'PAUSED':
                raise StoreConflict('Reconcile the existing Working run before resuming')
        self.store.change(row['project_id'], identity, lambda s: s.update(status='RUNNING', error=None,generation=s.get('generation',0)+1))
        self.gateway.platform.start(rig)
        self.tasks[identity] = asyncio.create_task(self.drive(row['project_id'], identity))
        return self.view(rig, identity)

    def preflight(self, rig_id, spec):
        platform = self.gateway.platform
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
        async with self.locks.setdefault(identity,asyncio.Lock()):
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
                                 for t in self.gateway.platform.store.snapshot(rig)['tasks'])
                if not unresolved and (worker.future is None or worker.future.done()):
                    # Caller cancellation can finish after a human-wait thread has
                    # already exited. Terminal owned tasks prove no provider remains.
                    worker.acknowledge_stopped()
                else:
                    self.store.change(row['project_id'],identity,lambda s:s.update(status='UNKNOWN',error='Planner process stop is uncertain; reconcile before resuming'))
        run = row['state'].get('run_id')
        if run and self.working.record(row['project_id'], run):
            await self.working.stop(row['project_id'], run)
        return self.view(rig, identity)

    @staticmethod
    def check_budget(spec, body):
        proposal = WorkingProposal.model_validate(body)
        seconds = proposal.budget.get('execution_seconds', proposal.budget.get('training_seconds'))
        limit = proposal.budget.get('output_bytes')
        if type(seconds) is not int or not 0 < seconds <= spec.execution_seconds:
            raise StoreConflict('Proposal exceeds or omits the delegated execution budget')
        if type(limit) is not int or not 0 < limit <= spec.output_bytes:
            raise StoreConflict('Proposal exceeds or omits the delegated output budget')
        if set(proposal.data_refs) - set(spec.resource_ids):
            raise StoreConflict('Proposal references context outside the operator grant')
        if proposal.research and proposal.research.model_dump() != spec.research.model_dump():
            raise StoreConflict('Proposal changed delegated research outputs')

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
                if not state.get('idea_id'):
                    topic = {'goal': spec.goal, 'benchmark_id': spec.benchmark_id,
                             'research_outputs': spec.research.model_dump(), 'previous_runs': state['runs'],
                             'instruction': 'Produce one concrete hypothesis to test within the operator goal. Reuse the selected benchmark; do not change its metric or split.'}
                    if state['runs']:
                        previous = self.working.detail(project, state['runs'][-1])
                        topic['previous_result'] = {'run_id':state['runs'][-1],'state':previous['state'],
                            'summary':(previous.get('working') or {}).get('summary'),
                            'result_metric':previous.get('result_metric'),'output':previous.get('output'),
                            'artifacts':previous.get('artifacts',[])}
                    idea = await asyncio.to_thread(runtime.invoke, 'ideation', topic, IDEA_SCHEMA, timeout=86400)
                    import jsonschema
                    jsonschema.validate(idea, IDEA_SCHEMA)
                    if state['runs']:
                        created = await self.planner.create_variant(project, state['runs'][-1], uuid.uuid4().hex,
                            idea['title'], idea['text'], idea['text'], spec.mode, spec.desired_output,
                            spec.research.model_dump(), ['research'], spec.benchmark_id)
                    else:
                        created = self.projects.save_idea(project, idea['text'], idea['title'], spec.mode,
                            spec.desired_output, spec.research.model_dump(), ['research'], spec.benchmark_id)
                    self.store.change(project, identity, lambda s: s.update(idea_id=created['id']))
                state = self.store.get(project, identity)['state']
                if not state.get('proposal_id'):
                    async with self.planner.lock:
                        context = self.projects.context_snapshot(project, state['idea_id'], spec.resource_ids)
                        self.projects.reserve_plan(project, state['idea_id'])
                    # This instruction is pinned before planning and is enforced again at approval.
                    context['snapshot']['workflow_constraints'] = {'execution_seconds': spec.execution_seconds,
                        'output_bytes': spec.output_bytes, 'accelerator': spec.accelerator, 'goal': spec.goal,
                        'grant_id': state['grant_id'], 'account': spec.account, 'max_runs': spec.max_runs,
                        'search': spec.search.model_dump(), 'approval_actor': spec.stages['approval'].actor}
                    from .store import canonical, digest
                    context['context_sha256'] = digest(canonical(context['snapshot']))
                    worker = RuntimeWorker(runtime, self.projects.directory(project) / 'automation' / identity / 'planner-state.json', uncertain_error=RuntimeUncertain)
                    self.workers[identity] = worker
                    await self.planner._plan(project, state['idea_id'], context, worker=worker)
                    if worker.state.get('status')=='unknown':
                        await worker.close(5)
                        raise RuntimeUncertain('Planner task outcome is unknown')
                    await worker.close(5)
                    proposal = next(iter(self.projects.proposals(project, state['idea_id'])), None)
                    if proposal is None or proposal['state'] not in {'AWAITING_APPROVAL', 'APPROVED'}:
                        raise StoreConflict('Proposal needs clarification or failed; use Idea to answer and resume explicitly')
                    self.store.change(project, identity, lambda s: s.update(proposal_id=proposal['id']))
                state = self.store.get(project, identity)['state']
                proposal = next(p for p in self.projects.proposals(project) if p['id'] == state['proposal_id'])
                self.check_budget(spec, proposal['body'])
                if not state.get('run_id'):
                    old = next((a for a in state['approvals'] if a['proposal_id'] == proposal['id']), None)
                    if old is None:
                        decision = await asyncio.to_thread(runtime.invoke, 'approval',
                            {'goal': spec.goal, 'proposal': proposal, 'operator_grant': spec.model_dump(),
                             'instruction': 'Approve only if this proposal implements the goal, uses the pinned benchmark/context and stays inside the operator grant. Return approve=false with a reason otherwise.'},
                            APPROVAL_SCHEMA, timeout=86400)
                        import jsonschema
                        jsonschema.validate(decision, APPROVAL_SCHEMA)
                        if not decision['approve']:
                            raise StoreConflict('Proposal rejected: ' + decision['reason'][:500])
                        actor = spec.stages['approval'].actor
                        if actor == 'agent' and not spec.allow_agent_approval:
                            raise StoreConflict('Agent has no delegated approval authority')
                        receipt = {'proposal_id': proposal['id'], 'version': proposal['version'],
                            'context_sha256': proposal['context_sha256'], 'budget': proposal['body']['budget'],
                            'actor': actor, 'seat': spec.stages['approval'].seat, 'grant_id': state['grant_id'],
                            'decision': decision}
                        self.store.change(project, identity, lambda s: s['approvals'].append(receipt))
                    runtime.check()
                    approved = await self.planner.approve(project, proposal['id'], proposal['version'], proposal['context_sha256'])
                    receipt = next(a for a in self.store.get(project,identity)['state']['approvals'] if a['proposal_id']==proposal['id'])
                    with self.projects.connection(project) as con:
                        con.execute('CREATE TABLE IF NOT EXISTS workflow_approval_actors(proposal_id TEXT PRIMARY KEY,workflow_id TEXT NOT NULL,receipt_json TEXT NOT NULL)')
                        con.execute('INSERT OR IGNORE INTO workflow_approval_actors VALUES(?,?,?)', (proposal['id'],identity,json.dumps(receipt)))
                    self.store.change(project, identity, lambda s: s.update(run_id=approved['id'], stage='execution'))
                state = self.store.get(project, identity)['state']
                run = state['run_id']
                if not self.working.record(project, run):
                    runtime.check()
                    await asyncio.to_thread(self.preflight,runtime.row['rig_id'],spec)
                    root = self.working.view.root(project, run)
                    root.mkdir(parents=True, exist_ok=True)
                    (root / 'workflow-provenance.json').write_text(json.dumps({'workflow_id': identity,
                        'rig_id': runtime.row['rig_id'], 'grant_id': state['grant_id'], 'approval': state['approvals'][-1],
                        'stages': spec.model_dump()['stages'], 'search': spec.search.model_dump()}, indent=2), encoding='utf-8')
                    await self.working.start(project, run, accelerator=spec.accelerator, ttl_seconds=spec.ttl_seconds, account=spec.account)
                while True:
                    runtime.check()
                    record = self.working.record(project, run)
                    if record and record.get('stop_confirmed'):
                        break
                    await asyncio.sleep(.5)
                if self.projects.run(project, run)['state'] != 'COMPLETED':
                    raise StoreConflict('Working failed or stopped; inspect its result before a new run')
                def finish(s):
                    if run not in s['runs']:
                        s['runs'].append(run)
                        s['iteration'] += 1
                    s.update(idea_id=None, proposal_id=None, run_id=None, stage='ideation')
                self.store.change(project, identity, finish)
        except (RuntimeCancelled, asyncio.CancelledError):
            self.store.change(project, identity, lambda s: s.update(status='PAUSED') if s.get('generation',0)==runtime.generation else None)
        except RuntimeUncertain:
            self.store.change(project, identity, lambda s: s.update(status='UNKNOWN', error='Reconcile the uncertain stage before continuing'))
        except Exception as exc:
            self.store.change(project, identity, lambda s: s.update(status='PAUSED', error=str(exc)[:1000]))

    async def close(self):
        self.closed = True
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        for worker in self.workers.values():
            await worker.close(5)

    async def reconcile(self, rig, identity):
        row = self.view(rig, identity)
        tasks = self.gateway.platform.store.snapshot(rig)['tasks']
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
