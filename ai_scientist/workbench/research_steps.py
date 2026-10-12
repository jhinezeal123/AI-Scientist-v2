"""Individual research operations shared by local and visual orchestration."""
import asyncio
import json
import uuid
from .agents.contracts import RuntimeUncertain
from .models import WorkingProposal
from .store import StoreConflict
from .worker import RuntimeWorker

APPROVAL_SCHEMA = {'type': 'object', 'required': ['approve', 'reason'], 'properties': {
    'approve': {'type': 'boolean'}, 'reason': {'type': 'string', 'minLength': 1}}, 'additionalProperties': False}

class ResearchSteps:
    def __init__(self, owner):
        self.owner = owner

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

    async def prepare_idea(self, runtime):
        from .research_ideation import prepare_idea
        await prepare_idea(runtime)

    async def prepare_proposal(self, runtime):
        owner = self.owner
        project, identity, spec = runtime.project, runtime.workflow, runtime.spec
        state = owner.store.get(project, identity)['state']
        if not state.get('proposal_id'):
            owner.store.change(project, identity, lambda s: s.update(revise_proposal=False))
            async with owner.planner.lock:
                context = owner.projects.context_snapshot(project, state['idea_id'], spec.resource_ids)
                owner.projects.reserve_plan(project, state['idea_id'])
            # This instruction is pinned before planning and is enforced again at approval.
            context['snapshot']['workflow_constraints'] = {'execution_seconds': spec.execution_seconds,
                'output_bytes': spec.output_bytes, 'accelerator': spec.accelerator, 'goal': spec.goal,
                'grant_id': state['grant_id'], 'account': spec.account, 'max_runs': spec.max_runs,
                'search': spec.search.model_dump(), 'approval_actor': spec.stages['approval'].actor}
            from .store import canonical, digest
            context['context_sha256'] = digest(canonical(context['snapshot']))
            worker = RuntimeWorker(runtime, owner.projects.directory(project) / 'automation' / identity / 'planner-state.json', uncertain_error=RuntimeUncertain)
            owner.workers[identity] = worker
            await owner.planner._plan(project, state['idea_id'], context, worker=worker)
            if worker.state.get('status')=='unknown':
                await worker.close(5)
                raise RuntimeUncertain('Planner task outcome is unknown')
            await worker.close(5)
            proposal = next(iter(owner.projects.proposals(project, state['idea_id'])), None)
            if proposal is None or proposal['state'] not in {'AWAITING_APPROVAL', 'APPROVED', 'NEEDS_CLARIFICATION'}:
                raise StoreConflict('Proposal needs clarification or failed; use Idea to answer and resume explicitly')
            owner.store.change(project, identity, lambda s: s.update(proposal_id=proposal['id']))
            if proposal['body']['needs_clarification']:
                owner.store.event(project,identity,'proposal','proposal_clarification_required',
                    proposal_id=proposal['id'], questions=proposal['body']['questions'], approval_allowed=False)

    async def approve_proposal(self, runtime):
        owner = self.owner
        project, identity, spec = runtime.project, runtime.workflow, runtime.spec
        state = owner.store.get(project, identity)['state']
        proposal = next(p for p in owner.projects.proposals(project) if p['id'] == state['proposal_id'])
        if not proposal['body']['needs_clarification']:
            owner.check_budget(spec, proposal['body'])
        if not state.get('run_id'):
            old = next((a for a in state['approvals'] if a['proposal_id'] == proposal['id']), None)
            if old is None:
                decision = await self._proposal_decision(runtime, proposal)
                if decision.get('revise_proposal'):
                    return
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
                owner.store.change(project, identity, lambda s: s['approvals'].append(receipt))
            runtime.check()
            approved = await owner.planner.approve(project, proposal['id'], proposal['version'], proposal['context_sha256'])
            receipt = next(a for a in owner.store.get(project,identity)['state']['approvals'] if a['proposal_id']==proposal['id'])
            with owner.projects.connection(project) as con:
                con.execute('CREATE TABLE IF NOT EXISTS workflow_approval_actors(proposal_id TEXT PRIMARY KEY,workflow_id TEXT NOT NULL,receipt_json TEXT NOT NULL)')
                con.execute('INSERT OR IGNORE INTO workflow_approval_actors VALUES(?,?,?)', (proposal['id'],identity,json.dumps(receipt)))
            owner.store.change(project, identity, lambda s: s.update(run_id=approved['id'], stage='execution'))

    async def _proposal_decision(self, runtime, proposal):
        from .proposal_discussion import ProposalDiscussion
        return await ProposalDiscussion(self.owner).decision(runtime, proposal, APPROVAL_SCHEMA)

    async def execute_run(self, runtime):
        owner = self.owner
        project, identity, spec = runtime.project, runtime.workflow, runtime.spec
        state = owner.store.get(project, identity)['state']
        proposal = next(p for p in owner.projects.proposals(project) if p['id'] == state['proposal_id'])
        state = owner.store.get(project, identity)['state']
        run = state['run_id']
        if not owner.working.record(project, run):
            if spec.require_run_approval:
                decision = await asyncio.to_thread(runtime.human, 'run_approval',
                    {'kind': 'review', 'candidate': {'run_id': run, 'proposal': {
                     k: proposal[k] for k in ('id','version','context_sha256','body')},
                     'account': spec.account, 'accelerator': spec.accelerator,
                     'ttl_seconds': spec.ttl_seconds}, 'instruction': 'Approve starting this exact run.'},
                    __import__('time').monotonic() + 86400, lambda: False)
                if not decision['approve']:
                    raise StoreConflict('Run rejected: ' + decision['reason'][:500])
            runtime.check()
            await asyncio.to_thread(owner.preflight,runtime.row['rig_id'],spec)
            root = owner.working.view.root(project, run)
            root.mkdir(parents=True, exist_ok=True)
            (root / 'workflow-provenance.json').write_text(json.dumps({'workflow_id': identity,
                'rig_id': runtime.row['rig_id'], 'grant_id': state['grant_id'], 'approval': state['approvals'][-1],
                'stages': spec.model_dump()['stages'], 'search': spec.search.model_dump()}, indent=2), encoding='utf-8')
            await owner.working.start(project, run, accelerator=spec.accelerator, ttl_seconds=spec.ttl_seconds, account=spec.account)

    async def collect_run(self, runtime):
        owner = self.owner
        project, identity, spec = runtime.project, runtime.workflow, runtime.spec
        state = owner.store.get(project, identity)['state']
        run = state['run_id']
        while True:
            runtime.check()
            record = owner.working.record(project, run)
            if record and record.get('stop_confirmed'):
                break
            await asyncio.sleep(.5)
        if owner.projects.run(project, run)['state'] != 'COMPLETED':
            raise StoreConflict('Working failed or stopped; inspect its result before a new run')
        def finish(s):
            if run not in s['runs']:
                s['runs'].append(run)
                s['iteration'] += 1
            s.update(idea_id=None, proposal_id=None, run_id=None, stage='ideation', proposal_round=0,
                     revise_proposal=False, proposal_revision_request={})
        owner.store.change(project, identity, finish)
