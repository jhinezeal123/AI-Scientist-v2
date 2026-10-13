"""One execution configuration and approval per authoritative project run."""
import json
from datetime import datetime, timezone

from .project_configuration import ProjectConfiguration
from .models import SearchOptions
from .run_configuration import RunConfiguration
from .store import StoreConflict, canonical, digest
from .workflow_store import WorkflowStore


class RunExecutionConfigurations:
    def __init__(self, projects):
        self.projects = projects

    @staticmethod
    def setup(con):
        con.execute('''CREATE TABLE IF NOT EXISTS run_execution_configuration(
            run_id TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,body_json TEXT NOT NULL,
            proposal_sha256 TEXT NOT NULL,approval_sha256 TEXT,approved_at TEXT)''')
        if 'planned_search_json' not in {row['name'] for row in con.execute('PRAGMA table_info(run_execution_configuration)')}:
            con.execute('ALTER TABLE run_execution_configuration ADD COLUMN planned_search_json TEXT')
        con.execute("UPDATE run_execution_configuration SET planned_search_json=COALESCE(json_extract(body_json,'$.search'),?) WHERE planned_search_json IS NULL",
                    (canonical(SearchOptions(enabled=False).model_dump(mode='json')),))

    @staticmethod
    def proposal(con, run):
        row = con.execute('''SELECT r.state,r.deleted_at,r.identity_json,p.id AS proposal_id,p.version,
            p.state AS proposal_state,p.context_sha256,p.context_snapshot_json,p.body_json
            FROM runs r JOIN proposals p ON p.id=r.proposal_id WHERE r.id=?''', (run,)).fetchone()
        if row is None:
            raise KeyError('Run không thuộc project này')
        return {**dict(row), 'body': json.loads(row['body_json']), 'snapshot': json.loads(row['context_snapshot_json'])}

    def seed_in_connection(self, con, run, proposal=None):
        self.setup(con)
        if con.execute('SELECT 1 FROM run_execution_configuration WHERE run_id=?', (run,)).fetchone():
            return
        proposal = proposal or self.proposal(con, run)
        defaults = {}
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='project_configuration'").fetchone():
            saved = con.execute('SELECT body_json FROM project_configuration').fetchone()
            if saved:
                defaults = ProjectConfiguration.normalize(json.loads(saved[0]))['run']
        config = RunConfiguration.from_workflow(defaults).model_dump(mode='json')
        constraints = proposal['snapshot'].get('workflow_constraints', {})
        budget = proposal['body'].get('budget', {})
        seconds = budget.get('execution_seconds', budget.get('training_seconds', config['execution_seconds']))
        config['execution_seconds'] = min(config['execution_seconds'], seconds)
        config['output_bytes'] = min(config['output_bytes'], budget.get('output_bytes', config['output_bytes']))
        config['ttl_seconds'] = max(config['ttl_seconds'], config['execution_seconds'] + 120)
        config['search'] = SearchOptions.model_validate(constraints.get('search') or {**config['search'], 'enabled':False}).model_dump(mode='json')
        if proposal['snapshot']['idea'].get('mode') != 'training_research':
            config['search'] = {**config['search'], 'enabled': False}
        # Existing sessions keep the environment that was actually submitted.
        session = None
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='working_runs'").fetchone():
            session = con.execute('SELECT * FROM working_runs WHERE run_id=?', (run,)).fetchone()
        if session:
            config.update(account=session['account'] or config['account'], accelerator=session['accelerator'],
                          ttl_seconds=session['ttl_seconds'])
            config['execution_seconds'] = min(config['execution_seconds'], max(1, session['ttl_seconds'] - 120))
        approval = digest(canonical({'proposal': proposal['context_sha256'], 'configuration': config})) if session else None
        con.execute('INSERT INTO run_execution_configuration VALUES(?,1,?,?,?,?,?)',
            (run, canonical(config), proposal['context_sha256'], approval,
             datetime.now(timezone.utc).isoformat() if session else None, canonical(config['search'])))

    @staticmethod
    def decode(row):
        return {'version': row['version'], 'configuration': json.loads(row['body_json']),
                'approved': bool(row['approval_sha256']), 'approval_sha256': row['approval_sha256'],
                'approved_at': row['approved_at']}

    def get(self, project, run):
        with self.projects.connection(project) as con:
            con.execute('BEGIN IMMEDIATE')
            self.setup(con)
            proposal = self.proposal(con, run)
            self.seed_in_connection(con, run, proposal)
            row = con.execute('SELECT * FROM run_execution_configuration WHERE run_id=?', (run,)).fetchone()
            if row['approval_sha256'] and row['approval_sha256'] != digest(canonical({
                    'proposal': row['proposal_sha256'], 'configuration': json.loads(row['body_json'])})):
                raise StoreConflict('Cấu hình đã ghim không khớp bản được duyệt')
            budget = proposal['body'].get('budget', {})
            result = self.decode(row)
            result.update(run_id=run, idea_id=proposal['snapshot']['idea']['id'],
                mode=proposal['snapshot']['idea'].get('mode', 'training_research'),
                benchmark=proposal['snapshot']['idea'].get('benchmark'),
                proposal_id=proposal['proposal_id'], proposal_version=proposal['version'],
                limits={'execution_seconds': budget.get('execution_seconds', budget.get('training_seconds')),
                        'output_bytes': budget.get('output_bytes')},
                planned_search=json.loads(row['planned_search_json']))
            result['execution_requirements'] = proposal['body'].get('execution_requirements')
            return result

    @staticmethod
    def compatibility(proposal, config, planned_search=None):
        requirements = proposal['body'].get('execution_requirements') or {}
        if requirements.get('accelerators') and config.accelerator not in requirements['accelerators']:
            raise StoreConflict('Accelerator không phù hợp proposal đã duyệt. Lập lại proposal với phần cứng này trước khi chạy.')
        budget = proposal['body'].get('budget', {})
        seconds = budget.get('execution_seconds', budget.get('training_seconds'))
        if seconds is not None and config.execution_seconds > seconds:
            raise StoreConflict('Budget vượt proposal đã duyệt. Lập lại proposal với cấu hình này trước khi chạy.')
        if budget.get('output_bytes') is not None and config.output_bytes > budget['output_bytes']:
            raise StoreConflict('Giới hạn output vượt proposal đã duyệt. Lập lại proposal trước khi chạy.')
        planned = planned_search or proposal['snapshot'].get('workflow_constraints', {}).get('search')
        if planned is not None and (planned.get('enabled') or config.search.enabled) and canonical(config.search.model_dump(mode='json')) != canonical(planned):
            raise StoreConflict('Chiến lược experiment manager đã đổi. Lập lại proposal với cấu hình này trước khi chạy.')
        if proposal['snapshot']['idea'].get('mode') != 'training_research' and config.search.enabled:
            raise StoreConflict('Experiment manager chỉ dùng cho Training/Research')

    def commit(self, project, run, version, config, *, approve=False, gate=None, remember=False):
        body = config.model_dump(mode='json')
        with self.projects.connection(project) as con:
            con.execute('BEGIN IMMEDIATE')
            self.setup(con)
            proposal = self.proposal(con, run)
            self.seed_in_connection(con, run, proposal)
            row = con.execute('SELECT * FROM run_execution_configuration WHERE run_id=?', (run,)).fetchone()
            if proposal['deleted_at'] or proposal['proposal_state'] != 'APPROVED':
                raise StoreConflict('Run phải có proposal hiện hành đã duyệt')
            if row['proposal_sha256'] != proposal['context_sha256']:
                raise StoreConflict('Proposal của run đã thay đổi')
            if row['approval_sha256']:
                if approve and json.loads(row['body_json']) == body and version in {row['version'], row['version'] - 1}:
                    return self.decode(row)
                raise StoreConflict('Cấu hình đã được duyệt cho run này; tạo lượt mới để thay đổi')
            if row['version'] != version:
                raise StoreConflict('Cấu hình run đã đổi; tải lại trước khi lưu')
            if proposal['state'] not in {'APPROVED', 'PREFLIGHT', 'FAILED'} or proposal['identity_json']:
                raise StoreConflict('Chỉ cấu hình run chưa bắt đầu')
            approval = None
            if approve:
                if not config.account.strip():
                    raise ValueError('Chọn account cho run này')
                self.compatibility(proposal, config, json.loads(row['planned_search_json']))
                approval = digest(canonical({'proposal': proposal['context_sha256'], 'configuration': body}))
            new_version = row['version'] + 1
            con.execute('UPDATE run_execution_configuration SET version=?,body_json=?,approval_sha256=?,approved_at=? WHERE run_id=?',
                (new_version, canonical(body), approval, datetime.now(timezone.utc).isoformat() if approve else None, run))
            if gate:
                identity, input_id = gate
                pending = con.execute('SELECT * FROM workflow_inputs WHERE id=? AND workflow_id=?', (input_id, identity)).fetchone()
                if not pending or pending['stage'] != 'run_approval' or pending['state'] != 'PENDING':
                    raise StoreConflict('Bước cấu hình run đã được xử lý')
                candidate = json.loads(pending['prompt_json']).get('candidate', {})
                if (candidate.get('run_id'), candidate.get('proposal', {}).get('context_sha256')) != (run, proposal['context_sha256']):
                    raise StoreConflict('Bước duyệt thuộc run hoặc proposal khác')
                WorkflowStore.answer_in_connection(con, identity, input_id,
                    {'approve': True, 'reason': 'Operator configured and approved this exact run', 'configuration_version': new_version})
                workflow = con.execute('SELECT state_json FROM research_workflows WHERE id=?', (identity,)).fetchone()
                state = json.loads(workflow[0])
                if state.get('run_id') != run:
                    raise StoreConflict('Workflow đã chuyển sang run khác')
                state.update(run_approval_id=run, run_configuration_version=new_version)
                con.execute('UPDATE research_workflows SET state_json=? WHERE id=?', (canonical(state), identity))
            if remember:
                ProjectConfiguration.setup(con, project)
                saved = con.execute('SELECT * FROM project_configuration').fetchone()
                defaults = ProjectConfiguration.normalize(json.loads(saved['body_json']))
                defaults['run'] = body
                con.execute('UPDATE project_configuration SET version=version+1,body_json=?', (canonical(defaults),))
        return self.get(project, run)

    def approved(self, project, run):
        value = self.get(project, run)
        if not value['approved']:
            raise StoreConflict('Run đang chờ cấu hình và duyệt môi trường chạy')
        return value

    def account(self, project, run):
        with self.projects.connection(project) as con:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE name='run_execution_configuration'").fetchone():
                return None
            row = con.execute('SELECT body_json FROM run_execution_configuration WHERE run_id=?', (run,)).fetchone()
            return json.loads(row[0]).get('account') or None if row else None

    def reserve_replan(self, project, run, version, config, flow_id=None):
        request = digest(canonical({'run': run, 'version': version, 'configuration': config.model_dump(mode='json')}))[:32]
        with self.projects.connection(project) as con:
            con.execute('BEGIN IMMEDIATE')
            self.setup(con)
            con.execute('CREATE TABLE IF NOT EXISTS run_replans(run_id TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,request_id TEXT NOT NULL,body_json TEXT NOT NULL)')
            existing = con.execute('SELECT * FROM run_replans WHERE run_id=?', (run,)).fetchone()
            if existing:
                if existing['request_id'] != request:
                    raise StoreConflict('Run này đã được thay bằng một yêu cầu lập proposal khác')
                return json.loads(existing['body_json'])
            proposal = self.proposal(con, run)
            self.seed_in_connection(con, run, proposal)
            row = con.execute('SELECT * FROM run_execution_configuration WHERE run_id=?', (run,)).fetchone()
            if row['version'] != version or row['approval_sha256'] or proposal['deleted_at']:
                raise StoreConflict('Run đã được duyệt hoặc cấu hình đã đổi; tải lại trước khi lập proposal')
            if proposal['state'] not in {'APPROVED','PREFLIGHT','FAILED'} or proposal['identity_json']:
                raise StoreConflict('Chỉ lập lại proposal cho run chưa bắt đầu')
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='working_runs'").fetchone() and con.execute('SELECT 1 FROM working_runs WHERE run_id=?', (run,)).fetchone():
                raise StoreConflict('Run đã mở phiên; tạo Improve sau khi phiên kết thúc')
            if proposal['snapshot']['idea'].get('mode') != 'training_research' and config.search.enabled:
                raise StoreConflict('Experiment manager chỉ dùng cho Training/Research')
            info = {'workflow_id': request, 'idea_id': digest(request + ':idea')[:32], 'previous_workflow_id': flow_id,
                    'previous_idea_id': proposal['snapshot']['idea']['id'],
                    'source_ids': [source['id'] for source in proposal['snapshot']['resources']]}
            con.execute('INSERT INTO run_replans VALUES(?,?,?)', (run, request, canonical(info)))
            con.execute("UPDATE runs SET state='CANCELLED',error='Đã yêu cầu proposal mới với cấu hình thực thi khác' WHERE id=?", (run,))
            return info
