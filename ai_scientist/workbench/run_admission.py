"""Review the exact run before admitting a remote session."""
import asyncio
import time
from .run_configuration import RunConfiguration
from .run_execution_configuration import RunExecutionConfigurations
from .store import StoreConflict
from .workflow_models import WorkflowSpec, STAGES


RUN_CONFIGURATION_SCHEMA = {'type': 'object', 'required': ['approve', 'reason'],
    'properties': {'approve': {'type': 'boolean'}, 'reason': {'type': 'string', 'minLength': 1},
                   'configuration_version': {'type': 'integer', 'minimum': 1}},
    'additionalProperties': False,
    'allOf': [{'if': {'properties': {'approve': {'const': True}}}, 'then': {'required': ['configuration_version']}}]}


class RunAdmission:
    def __init__(self, owner):
        self.owner = owner
        self.configurations = RunExecutionConfigurations(owner.projects)

    def owning(self, project, run):
        controls = getattr(self.owner, 'controls', None)
        return controls.owning(project, run=run) if controls else None

    def save(self, project, run, version, config, remember=False):
        if config.account and self.owner.working.accounts:
            self.owner.working.accounts.require(config.account)
        flow = self.owning(project, run)
        if flow and (flow['spec'].get('run_setup') != 'per_run' or not flow['spec']['require_run_approval']):
            raise StoreConflict('Run này dùng môi trường đã được cấp trước; tạo lượt mới để thay đổi')
        return self.configurations.commit(project, run, version, config, remember=remember)

    async def start(self, project, run, version, config, remember=False):
        if self.owner.working.accounts:
            self.owner.working.accounts.require(config.account)
        flow = self.owning(project, run)
        gate = None
        if flow:
            if flow['spec'].get('run_setup') != 'per_run' or not flow['spec']['require_run_approval']:
                raise StoreConflict('Workflow này đã cấp môi trường trước; chỉ duyệt đúng bước đang chờ')
            existing = self.configurations.get(project, run)
            if existing['approved'] and existing['configuration'] == config.model_dump(mode='json'):
                return {'workflow_id': flow['id'], 'pending': True}
            pending = self.owner.controls.pending(project, flow['id'], 'run_approval')
            gate = (flow['id'], pending['id'])
        saved = self.configurations.commit(project, run, version, config, approve=True, gate=gate, remember=remember)
        if flow:
            return {'workflow_id': flow['id'], 'pending': True, 'configuration': saved}
        record = self.owner.working.record(project, run)
        if record:
            return {'run_id': run, 'state': record.get('state', record.get('phase')), 'configuration': saved}
        return await self.owner.working.start(project, run, accelerator=config.accelerator,
            ttl_seconds=config.ttl_seconds, search=config.search.model_dump(), account=config.account)

    def delegated(self, runtime):
        state = self.owner.store.get(runtime.project, runtime.workflow)['state']
        value = self.configurations.get(runtime.project, state['run_id'])
        if value['approved']:
            return value
        config = RunConfiguration.from_workflow(runtime.spec.model_dump(mode='json'))
        limits = value['limits']
        config.execution_seconds = min(config.execution_seconds, limits['execution_seconds'] or config.execution_seconds)
        config.output_bytes = min(config.output_bytes, limits['output_bytes'] or config.output_bytes)
        return self.configurations.commit(runtime.project, state['run_id'], value['version'], config, approve=True)

    async def replan(self, project, run, version, config):
        flow = self.owning(project, run)
        if flow and (flow['spec'].get('run_setup') != 'per_run' or not flow['spec']['require_run_approval']):
            raise StoreConflict('Tạo một lượt Hybrid mới để thay đổi phạm vi đã được cấp trước')
        info = self.configurations.reserve_replan(project, run, version, config, flow['id'] if flow else None)
        identity = info['workflow_id']
        try:
            existing = self.owner.store.get(project, identity)
        except KeyError:
            existing = None
        if existing and existing['state'].get('entry_idea_id'):
            return {'workflow_id': identity, 'idea_id': existing['state']['entry_idea_id']}
        previous = self.owner.store.get(project, info['previous_workflow_id']) if info['previous_workflow_id'] else None
        if previous and previous['state']['status'] != 'CANCELLED':
            await self.owner.pause(project, previous['id'])
            self.owner.store.change(project, previous['id'], lambda s: s.update(status='CANCELLED', replaced_by=identity))
        old = self.owner.projects.idea(project, info['previous_idea_id'])
        title = (old['title'] or 'Idea')[:58] + ' · Cấu hình lại'
        if old.get('variant'):
            variant = old['variant']
            idea = await self.owner.planner.create_variant(project, variant['parent_run_id'], identity, title,
                variant['purpose'], variant['change_summary'], old['mode'], old['desired_output'], old.get('research'),
                old.get('tags'), old.get('benchmark_id'))
        else:
            idea = self.owner.projects.save_idea(project, old['text'], title, old['mode'], old['desired_output'],
                old.get('research'), old.get('tags'), old.get('benchmark_id'), idea_id=info['idea_id'])
        selected = self.owner.controls.configuration.selection(project, idea['id'])
        if selected['resource_ids'] != info['source_ids']:
            self.owner.controls.configuration.select(project, idea['id'], info['source_ids'], selected['version'])
        template = previous['spec'] if previous else (self.owner.controls.configuration.get(project)['workflow'] or {})
        stages = template.get('stages') or {s: {'actor': 'human' if s in {'ideation','approval'} else 'agent', 'preset_id': 'default'} for s in STAGES}
        stages = {**stages, 'ideation': {'actor': 'human'}, 'approval': {'actor': 'human'}}
        spec = WorkflowSpec.model_validate({**template, **config.model_dump(mode='json'), 'stages': stages,
            'goal': old['text'][:10000], 'mode': old['mode'], 'benchmark_id': old.get('benchmark_id'),
            'desired_output': old['desired_output'], 'research': old.get('research') or {},
            'resource_ids': info['source_ids'], 'run_setup': 'per_run', 'require_run_approval': True,
            'allow_agent_approval': False, 'max_runs': 1})
        if not existing:
            self.owner.create(project, identity, spec, save_defaults=False)
            self.owner.store.change(project, identity, lambda s: s.update(execution_preference=config.model_dump(mode='json')))
        try:
            await self.owner.start(project, identity, idea_id=idea['id'])
        except (StoreConflict, ValueError) as exc:
            self.owner.store.change(project, identity, lambda s: s.update(error=str(exc), entry_idea_id=idea['id']))
        return {'workflow_id': identity, 'idea_id': idea['id']}

    async def review(self, runtime):
        state = self.owner.store.get(runtime.project, runtime.workflow)['state']
        proposal = next(p for p in self.owner.projects.proposals(runtime.project) if p['id'] == state['proposal_id'])
        if runtime.spec.run_setup == 'per_run':
            decision = await asyncio.to_thread(runtime.human, 'run_approval',
                {'kind': 'run_configuration', 'schema': RUN_CONFIGURATION_SCHEMA,
                 'candidate': {'run_id': state['run_id'], 'project_id': runtime.project,
                    'proposal': {k: proposal[k] for k in ('id', 'version', 'context_sha256', 'body')}},
                 'instruction': 'Configure and approve this run in the Run tab.'},
                time.monotonic() + 86400, lambda: False)
            if decision['approve']:
                value = self.configurations.approved(runtime.project, state['run_id'])
                if value['version'] != decision['configuration_version']:
                    raise StoreConflict('Cấu hình run đã duyệt không khớp bước đang chờ')
            return decision
        return await asyncio.to_thread(runtime.human, 'run_approval',
            {'kind': 'review', 'candidate': {'run_id': state['run_id'], 'proposal': {
             k: proposal[k] for k in ('id', 'version', 'context_sha256', 'body')},
             'account': runtime.spec.account, 'accelerator': runtime.spec.accelerator,
             'ttl_seconds': runtime.spec.ttl_seconds}, 'instruction': 'Approve starting this exact run.'},
            time.monotonic() + 86400, lambda: False)
