"""Shared project commands bind Idea/Run actions to the owning n8n gate."""
from .project_configuration import ProjectConfiguration
from .store import StoreConflict, canonical, digest
from .workflow_models import WorkflowSpec


class ProjectWorkflowControls:
    def __init__(self, owner):
        self.owner = owner
        self.configuration = ProjectConfiguration(owner.projects)

    def owning(self, project, *, idea=None, proposal=None, run=None):
        for row in self.owner.list(project):
            state = row['state']
            if row['archived'] or state['status'] in {'DONE','CANCELLED'}:
                continue
            if ((idea and state.get('idea_id') == idea) or (proposal and state.get('proposal_id') == proposal)
                    or (run and state.get('run_id') == run)):
                return row

    def pending(self, project, flow, stage):
        row = self.owner.current(project, flow)
        if row['state']['status'] != 'WAITING':
            raise StoreConflict('Workflow chưa chờ thao tác này; tải lại hoặc tiếp tục workflow')
        pending = next((i for i in row['inputs'] if i['stage'] == stage and i['state'] == 'PENDING'), None)
        if pending is None:
            raise StoreConflict('Bước này đã được xử lý hoặc chưa tới lượt')
        return pending

    def proposal_answer(self, project, candidate, *, message=None, request_id=None, approve=None):
        flow = self.owning(project, proposal=candidate['id'])
        if flow is None:
            return None
        pending = self.pending(project, flow['id'], 'approval')
        pinned = pending['prompt'].get('candidate', {})
        if (pinned.get('id'), pinned.get('version'), pinned.get('context_sha256')) != (candidate['id'], candidate['version'], candidate['context_sha256']):
            raise StoreConflict('Proposal đang chờ đã thay đổi; tải lại trước khi trả lời')
        result = ({'message': message, 'request_id': request_id} if message is not None else
                  {'approve': bool(approve), 'reason': 'Operator approved this exact candidate' if approve else 'Operator rejected this candidate'})
        self.owner.store.answer(project, flow['id'], pending['id'], result)
        return {'workflow_id': flow['id'], 'pending': True}

    def configure_idea(self, project, identity, idea_id, *, input_id=None):
        """Freeze the selected idea's effective settings before any provider call."""
        owner = self.owner
        row = owner.store.get(project, identity)
        if row['state'].get('idea_id'):
            if row['state']['idea_id'] != idea_id:
                raise StoreConflict('Workflow đã gắn với một idea khác')
            return
        idea = owner.projects.idea(project, idea_id)
        if idea['deleted_at'] or idea['mode'] == 'benchmark' or idea['state'] in {'PLANNING','APPROVED'}:
            raise StoreConflict('Chọn một idea chưa duyệt và chưa có lượt lập proposal đang chạy')
        if idea['mode'] == 'training_research':
            if not idea.get('benchmark_id'):
                raise StoreConflict('Chọn benchmark trong Idea trước khi lập proposal')
            from .benchmarks import BenchmarkCatalog
            BenchmarkCatalog(owner.projects).require(project, idea['benchmark_id'])
        elif not idea['desired_output'].strip():
            raise StoreConflict('Nhập đầu ra mong muốn trong Idea trước khi lập proposal')
        parent = row['state'].get('parent_run_id') if not row['state']['runs'] else row['state']['runs'][-1]
        if parent and (idea.get('variant') or {}).get('parent_run_id') != parent:
            raise StoreConflict('Tạo idea Improve từ run cha trong tab Run để kế thừa kết quả đã ghim')
        other = self.owning(project, idea=idea_id)
        if other and other['id'] != identity:
            raise StoreConflict('Idea này đã thuộc một workflow khác')
        sources = self.configuration.selection(project, idea_id)['resource_ids']
        self.configuration.validate_sources(project, sources)
        spec = WorkflowSpec.model_validate({**row['spec'], 'mode': idea['mode'],
            'desired_output': idea['desired_output'], 'benchmark_id': idea['benchmark_id'],
            'research': idea['research'] or {}, 'resource_ids': sources,
            'search': {**row['spec']['search'], 'enabled': row['spec']['search']['enabled'] and idea['mode']=='training_research'}})
        fingerprints = {r['id']: digest(canonical(r)) for r in owner.projects.resources(project) if r['id'] in sources}
        owner.store.attach_idea(project, identity, idea_id, spec, fingerprints, input_id=input_id)
        owner.write_grant(project, identity)

    def choose_idea(self, project, identity, input_id, idea_id):
        pending = self.pending(project, identity, 'ideation')
        if pending['id'] != input_id:
            raise StoreConflict('Yêu cầu chọn idea đã thay đổi')
        self.configure_idea(project,identity,idea_id,input_id=input_id)

