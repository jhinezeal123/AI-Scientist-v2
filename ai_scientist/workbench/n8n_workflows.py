"""Project grants and individual operations. n8n owns ordering and repetition."""
import asyncio
import json
from urllib.error import HTTPError

from .agents.contracts import RuntimeCancelled, RuntimeUncertain
from .n8n_agent_turns import N8nAgentTurns
from .n8n_client import N8nClient
from .n8n_callbacks import StepCallbacks
from .preset_stage_executor import PresetStageExecutor
from .research_steps import ResearchSteps
from .run_phases import RunPhases, RUN_PHASES, enabled as phase_enabled
from .research_candidates import generate_candidates, assess_candidates, select_candidate
from .stage_runtime import StageRuntime
from .store import canonical, digest, StoreConflict
from .workflow_models import WorkflowSpec
from .workflow_store import WorkflowStore

PHASES = ('ideation', 'literature', 'idea_selection', 'proposal', 'approval', 'run_approval', 'execution', *RUN_PHASES, 'collect')


class N8nResearchWorkflows:
    check_budget = staticmethod(ResearchSteps.check_budget)

    def __init__(self, planner, working, gateway, *, client=None):
        self.planner, self.working, self.gateway = planner, working, gateway
        self.projects = planner.store
        self.store = WorkflowStore(self.projects)
        self.client = client or N8nClient(self.projects.workspace)
        self.steps = ResearchSteps(self)
        self.executor = PresetStageExecutor(self)
        self.agent_turns = N8nAgentTurns(self.client, self.executor)
        self.callbacks = StepCallbacks(self.store, self.client)
        self.run_phases = RunPhases(self)
        self.tasks, self.workers, self.locks = {}, {}, {}
        self.closed = False

    def create(self, project, identity, spec):
        self.projects.project(project)
        from _ai_scientist_agent_management.presets import Presets
        presets = {p['id']: p for p in Presets(self.gateway.control_store).list()}
        bindings = {}
        for stage, binding in spec.stages.items():
            if binding.actor == 'human':
                bindings[stage] = {'actor': 'human', 'seat': stage}
                continue
            preset = presets.get(binding.preset_id or 'default')
            if preset is None:
                raise ValueError('Choose an existing Config agent preset for ' + stage)
            bindings[stage] = {'actor': 'agent', 'seat': stage, 'preset_id': preset['id'],
                               'harness': preset['harness'], 'model': preset['model'], 'ask': binding.ask}
        spec = WorkflowSpec.model_validate({**spec.model_dump(), 'stages': bindings})
        if spec.benchmark_id:
            from .benchmarks import BenchmarkCatalog
            BenchmarkCatalog(self.projects).require(project, spec.benchmark_id)
        if self.working.accounts:
            self.working.accounts.require(spec.account)
        resources = self.projects.resources(project)
        if set(spec.resource_ids) - {r['id'] for r in resources}:
            raise ValueError('Context is outside the selected project')
        fingerprints = {r['id']: digest(canonical(r)) for r in resources if r['id'] in spec.resource_ids}
        row = self.store.create(project, project, identity, spec, fingerprints)
        folder = self.projects.directory(project) / 'automation' / identity
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'grant.json').write_text(json.dumps({'workflow_id': identity, 'project_id': project,
            'spec': row['spec'], 'grant_id': row['state']['grant_id'], 'sources': fingerprints,
            'n8n_workflow_id': 'workbenchResearch'}, ensure_ascii=False, indent=2), encoding='utf-8')
        return self.view(project, identity)

    def list(self, project):
        self.projects.project(project)
        return [self.history_view(project, row) for row in self.store.list(project)]

    @staticmethod
    def history_view(project, row):
        row['project_id'] = project
        for job in row['state'].get('step_jobs', {}).values():
            if 'callback' in job:
                job['callback'] = {k: v for k, v in job['callback'].items() if k != 'resume_url'}
        row['archived'] = row['rig_id'] != project
        if row['archived']:
            row['state'] = {**row['state'], 'original_status': row['state']['status'],
                'status': 'ARCHIVED', 'error': 'Workflow Team cũ đã được lưu làm lịch sử. Tạo cấu hình n8n mới để tiếp tục project.'}
        return row

    def view(self, project, identity):
        self.projects.project(project)
        row = self.history_view(project, self.store.get(project, identity))
        row['inputs'] = self.store.inputs(project, identity)
        row['n8n'] = self.client.status()
        execution = row['state'].get('n8n_execution_id') if not row['archived'] else None
        jobs = row['state'].get('step_jobs', {})
        row['n8n']['callback_failed'] = any(j.get('callback', {}).get('delivery') == 'FAILED' for j in jobs.values())
        row['n8n']['execution_url'] = self.client.base_url + '/workflow/workbenchResearch/executions/' + execution if execution else None
        if row['state'].get('run_id'):
            row['run'] = self.working.detail(project, row['state']['run_id'])
        return row

    def current(self, project, identity):
        row = self.view(project, identity)
        if row['archived']:
            raise StoreConflict('Workflow Team cũ chỉ dùng để xem lịch sử; tạo cấu hình n8n mới')
        return row

    def runtime_for_run(self, key):
        project, run = key
        for row in self.list(project):
            if not row['archived'] and (row['state'].get('run_id') == run or run in row['state']['runs']):
                runtime = StageRuntime(self, project, row['id'])
                runtime.run_phases = self.run_phases.bind(runtime, run)
                return runtime
        return self.planner.worker.runtime

    def preflight(self, project, spec):
        self.projects.project(project)
        if spec.research.vlm:
            vision = spec.stages['vision']
            harness = next((h for h in self.gateway.control_store.harnesses() if h.id == vision.harness),None)
            if vision.actor != 'agent' or harness is None or harness.kind not in {'native_codex','native_claude','acp'}:
                raise StoreConflict('VLM cần preset Codex, Claude hoặc ACP có image capability; chọn preset riêng cho VLM')
        checked = set()
        for stage in spec.active_stages():
            binding = spec.stages[stage]
            if binding.actor != 'agent' or binding.harness in checked:
                continue
            harness = next((h for h in self.gateway.control_store.harnesses() if h.id == binding.harness), None)
            if harness is None or not harness.enabled or harness.archived:
                raise StoreConflict('Configure the saved preset provider for ' + stage)
            if not self.gateway.harness_catalog.resolve(binding.harness).probe().get('ready'):
                raise StoreConflict('Provider for ' + stage + ' is not ready; open Config agent')
            checked.add(binding.harness)

    async def start(self, project, identity):
        async with self.locks.setdefault(project, asyncio.Lock()):
            row = self.current(project, identity)
            if row['state']['status'] in {'RUNNING', 'WAITING'}:
                return row
            if row['state']['status'] in {'DONE', 'UNKNOWN'}:
                raise StoreConflict('Completed/uncertain workflow cannot be replayed')
            if not row['n8n']['ready']:
                raise StoreConflict('Start local n8n before starting this workflow')
            if any(r['id'] != identity and r['state']['status'] in {'RUNNING', 'WAITING', 'UNKNOWN'} for r in self.list(project)):
                raise StoreConflict('Stop or reconcile the current project workflow first')
            await asyncio.to_thread(self.preflight, project, WorkflowSpec.model_validate(row['spec']))
            run = row['state'].get('run_id')
            if run and self.working.record(project, run) and not self.working.record(project, run).get('stop_confirmed'):
                raise StoreConflict('Reconcile the existing Working run before resuming')
            if any(v.get('status') in {'RUNNING', 'UNKNOWN'} for v in row['state'].get('invocations', {}).values()):
                raise RuntimeUncertain('Reconcile the previous provider call first')
            state = self.store.change(project, identity, lambda s: s.update(status='RUNNING', error=None,
                generation=s.get('generation', 0)+1, step_jobs={}))['state']
            try:
                await asyncio.to_thread(self.client.dispatch, 'research', {'project_id': project, 'workflow_id': identity,
                    'generation': state['generation'], 'iteration': state['iteration']})
            except HTTPError as exc:
                self.store.change(project, identity, lambda s: s.update(status='PAUSED', error='n8n workflow is unavailable; import and publish the supplied workflows'))
                raise StoreConflict('n8n workflow is unavailable') from exc
            except OSError as exc:
                self.store.change(project, identity, lambda s: s.update(status='UNKNOWN', error='n8n dispatch outcome is uncertain; inspect its executions before resuming'))
                raise StoreConflict('n8n dispatch outcome is uncertain') from exc
            return self.view(project, identity)

    @staticmethod
    def step_key(iteration, step, proposal_round=0):
        return f'{iteration}:{step}' + (f':{proposal_round}' if step in {'proposal','approval'} and proposal_round else '')

    async def step(self, project, identity, generation, iteration, step, execution_id='', resume_url='', proposal_round=0):
        if step not in PHASES:
            raise ValueError('Unknown research operation')
        if resume_url:
            self.client.validate_resume_url(resume_url, execution_id, generation, iteration, step, proposal_round)
        async with self.locks.setdefault(project, asyncio.Lock()):
            row = self.store.get(project, identity)
            state = row['state']
            if row['rig_id'] != project or generation != state.get('generation'):
                raise StoreConflict('This n8n execution has no current project grant')
            key = self.step_key(iteration, step, proposal_round)
            job = state.get('step_jobs', {}).get(key)
            if resume_url:
                if job and job.get('callback') and job['callback']['resume_url'] != resume_url:
                    raise StoreConflict('This research step belongs to a different n8n execution')
                callback = {'resume_url': resume_url, 'generation': generation,
                            'request': {'project_id': project, 'workflow_id': identity, 'generation': generation,
                                        'iteration': iteration, 'step': step, 'request_round':proposal_round,
                                        'proposal_round':proposal_round},
                            'delivery': 'PENDING', 'attempts': 0}
                if job:
                    self.store.change(project, identity, lambda s: s['step_jobs'][key].setdefault('callback', callback))
            if job and job['status'] in {'DONE', 'FAILED'}:
                self.callbacks.schedule(project, identity, key)
                return job['view']
            if state['status'] not in {'RUNNING', 'WAITING'}:
                if resume_url:
                    raise StoreConflict('Workflow stopped; this execution cannot start another step')
                return self.step_view(project, identity, generation, iteration, step, 'FAILED', state.get('error') or 'Workflow stopped')
            if iteration != state['iteration']:
                raise StoreConflict('n8n iteration does not match the saved project grant')
            if step in {'proposal','approval'} and proposal_round != state.get('proposal_round',0):
                raise StoreConflict('This proposal discussion round is stale')
            if job is None:
                spec = WorkflowSpec.model_validate(row['spec'])
                preceding = [phase for phase in PHASES[:PHASES.index(step)]
                             if phase not in RUN_PHASES or phase_enabled(spec, phase)]
                predecessor = len(preceding)-1
                previous_key = self.step_key(iteration, preceding[-1], state.get('proposal_round',0)) if preceding else f'{iteration-1}:collect'
                if step == 'proposal' and proposal_round:
                    previous_key = self.step_key(iteration,'approval',proposal_round-1)
                    if not state.get('step_jobs',{}).get(previous_key,{}).get('view',{}).get('revise_proposal'):
                        if state.get('proposal_revision_request',{}).get('round') != proposal_round:
                            raise StoreConflict('Only a human message can request another proposal turn')
                        # A restarted execution begins with ideation again. The
                        # saved human intent still authorizes this planning turn.
                        previous_key = self.step_key(iteration,'idea_selection')
                if predecessor >= 0 and state.get('step_jobs', {}).get(previous_key, {}).get('status') != 'DONE':
                    raise StoreConflict('Complete the preceding research operation first')
                # A next-step request from the same execution confirms receipt
                # even when the previous callback HTTP response was lost.
                if resume_url and state.get('n8n_execution_id') == execution_id:
                    self.store.change(project, identity, lambda s: s.get('step_jobs', {}).get(previous_key, {})
                        .get('callback', {}).update(delivery='DELIVERED'))
                if any(v['status'] == 'RUNNING' for v in state.get('step_jobs', {}).values()):
                    raise StoreConflict('A research operation is already active')
                self.store.change(project, identity, lambda s: (s.setdefault('step_jobs', {}).__setitem__(key,
                    {'status': 'RUNNING', **({'callback': callback} if resume_url else {})}),
                    s.update(n8n_execution_id=execution_id)))
                self.tasks[(identity, key)] = asyncio.create_task(self._step(project, identity, generation, iteration, step, proposal_round))
            return self.step_view(project, identity, generation, iteration, step, 'RUNNING', proposal_round=proposal_round)

    def step_view(self, project, identity, generation, iteration, step, status, error='', proposal_round=0):
        state = self.store.get(project, identity)['state']
        proposal = next((p for p in self.projects.proposals(project) if p['id']==state.get('proposal_id')),None)
        needs_clarification = bool(proposal and proposal['body']['needs_clarification'])
        return {'project_id': project, 'workflow_id': identity, 'generation': generation,
                'search_enabled':WorkflowSpec.model_validate(self.store.get(project, identity)['spec']).search.enabled,
                'iteration': state['iteration'] if status == 'DONE' else iteration, 'step': step,
                'pending': status == 'RUNNING', 'failed': status == 'FAILED',
                'continue': state['iteration'] < WorkflowSpec.model_validate(self.store.get(project, identity)['spec']).max_runs,
                'status': status, 'error': error,
                'request_round':proposal_round,'proposal_round':state.get('proposal_round',0),
                'needs_clarification':needs_clarification,
                'approval_allowed':bool(proposal and proposal['state']=='AWAITING_APPROVAL' and not needs_clarification),
                'clarification_questions':proposal['body'].get('questions',[]) if needs_clarification else [],
                'revise_proposal':step=='approval' and status=='DONE' and bool(state.get('revise_proposal'))}

    async def _step(self, project, identity, generation, iteration, step, proposal_round=0):
        runtime = StageRuntime(self, project, identity)
        key = self.step_key(iteration, step, proposal_round)
        status, error = 'DONE', ''
        try:
            runtime.check()
            runtime.context()
            if iteration >= runtime.spec.max_runs:
                raise StoreConflict('Operator run limit reached')
            operation = {'ideation': generate_candidates, 'literature': assess_candidates,
                         'idea_selection': select_candidate, 'proposal': self.steps.prepare_proposal,
                         'approval': self.steps.approve_proposal, 'run_approval': self.approve_run,
                         'execution': self.steps.execute_run, 'collect': self.steps.collect_run}.get(step)
            if step in RUN_PHASES:
                result = await self.run_phases.advance(runtime, step)
                self.store.change(project, identity, lambda s: s['step_jobs'][key].update(phase_result=result))
            else:
                await operation(runtime)
            if step == 'collect' and self.store.get(project, identity)['state']['iteration'] >= runtime.spec.max_runs:
                self.store.change(project, identity, lambda s: s.update(status='DONE', stage='review'))
        except RuntimeUncertain as exc:
            status, error = 'FAILED', str(exc)[:1000]
            self.store.change(project, identity, lambda s: s.update(status='UNKNOWN', error=error)
                              if s.get('generation') == generation else None)
        except BaseException as exc:
            status, error = 'FAILED', str(exc)[:1000] or 'Workflow stopped'
            uncertain = any(v.get('status') in {'RUNNING', 'UNKNOWN'} for v in self.store.get(project, identity)['state'].get('invocations', {}).values())
            self.store.change(project, identity, lambda s: s.update(status='UNKNOWN' if uncertain else 'PAUSED', error=error)
                              if s.get('generation') == generation else None)
        view = self.step_view(project, identity, generation, iteration, step, status, error, proposal_round)
        view.update(self.store.get(project, identity)['state'].get('step_jobs', {}).get(key, {}).get('phase_result', {}))
        self._complete_step(project, identity, generation, key, status, view)
        self.callbacks.schedule(project, identity, key)

    def _complete_step(self, project, identity, generation, key, status, view):
        self.store.change(project, identity, lambda s: s.setdefault('step_jobs', {}).setdefault(key, {}).update(status=status, view=view)
                          if s.get('generation') == generation else None)

    async def approve_run(self, runtime):
        if not runtime.spec.require_run_approval:
            return
        state = self.store.get(runtime.project, runtime.workflow)['state']
        proposal = next(p for p in self.projects.proposals(runtime.project) if p['id'] == state['proposal_id'])
        decision = await asyncio.to_thread(runtime.human, 'run_approval',
            {'kind': 'review', 'candidate': {'run_id': state['run_id'], 'proposal': {
             k: proposal[k] for k in ('id', 'version', 'context_sha256', 'body')},
             'account': runtime.spec.account, 'accelerator': runtime.spec.accelerator,
             'ttl_seconds': runtime.spec.ttl_seconds}, 'instruction': 'Approve starting this exact run.'},
            __import__('time').monotonic()+86400, lambda: False)
        if not decision['approve']:
            raise StoreConflict('Run rejected: ' + decision['reason'][:500])

    async def pause(self, project, identity):
        row = self.current(project, identity)
        if row['state']['status'] == 'DONE':
            return row
        self.store.change(project, identity, lambda s: s.update(status='PAUSED', generation=s.get('generation', 0)+1))
        self.executor.interrupt(identity)
        for (workflow, _), task in list(self.tasks.items()):
            if workflow == identity and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        if identity in self.workers:
            await self.workers[identity].close(5)
        if row['state'].get('run_id') and self.working.record(project, row['state']['run_id']):
            await self.working.stop(project, row['state']['run_id'])
        self.callbacks.retry(project, identity)
        return self.view(project, identity)

    async def reconcile(self, project, identity):
        row = self.current(project, identity)
        if row['state']['status'] == 'DONE':
            return row
        if row['state']['status'] in {'RUNNING', 'WAITING'}:
            raise StoreConflict('Dừng workflow trước khi đối soát')
        if any(key[0] == identity for key in self.executor.active):
            raise StoreConflict('Provider process is still stopping')
        # Provider process groups close with the backend; an unknown external
        # action remains visible and requires Working's existing reconciliation.
        run = row['state'].get('run_id')
        if run and self.working.record(project, run):
            await self.working.reconcile(project, run)
            if not self.working.record(project, run).get('stop_confirmed'):
                raise StoreConflict('Kaggle session stop is still uncertain')
        from _ai_scientist_agent_management.processes import process_identity
        for invocation, value in row['state'].get('invocations', {}).items():
            if value.get('status') not in {'RUNNING', 'UNKNOWN'}:
                continue
            stopped = value.get('receipt', {}).get('tree_stopped')
            if not stopped and value.get('pid') and __import__('os').name == 'nt':
                current = process_identity(value['pid'])
                stopped = current is None or (value.get('birth_identity') is not None and current != value['birth_identity'])
            if not stopped and value.get('pid'):
                raise StoreConflict('The previous provider process has not been confirmed stopped')
            self.store.change(project, identity, lambda s: s['invocations'][invocation].update(status='FAILED',
                receipt={'tree_stopped': True, 'process_exited': True, 'reconciled': True}))
        self.store.change(project, identity, lambda s: s.update(status='PAUSED', error=None))
        return self.view(project, identity)

    def recover(self):
        for project in self.projects.list_projects():
            for row in self.list(project['id']):
                if row['state']['status'] in {'RUNNING', 'WAITING'}:
                    uncertain = any(v.get('status') == 'RUNNING' for v in row['state'].get('invocations', {}).values())
                    self.store.change(project['id'], row['id'], lambda s: s.update(status='UNKNOWN' if uncertain else 'PAUSED',
                        generation=s.get('generation', 0)+1, error='Backend restarted; inspect the saved run and n8n execution before resuming'))
                if not row['archived']:
                    self.callbacks.retry(project['id'], row['id'])

    async def close(self):
        self.closed = True
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        await self.callbacks.close()
        for worker in self.workers.values():
            await worker.close(5)
        await self.agent_turns.close()
