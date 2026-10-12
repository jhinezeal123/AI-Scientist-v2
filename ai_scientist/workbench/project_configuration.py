"""Project defaults and deliberate per-idea context overrides."""
import json
from .store import StoreConflict, canonical
from .run_configuration import RunConfiguration


class ProjectConfiguration:
    def __init__(self, projects):
        self.projects = projects

    @staticmethod
    def setup(con, project=None):
        con.execute('CREATE TABLE IF NOT EXISTS project_configuration(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL,body_json TEXT NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS idea_context(idea_id TEXT PRIMARY KEY,version INTEGER NOT NULL,resource_ids_json TEXT)')
        if not con.execute('SELECT 1 FROM project_configuration').fetchone():
            # Existing saved grants remain immutable. Seed future defaults once.
            workflow = None
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='research_workflows'").fetchone():
                for row in con.execute('SELECT spec_json,rig_id FROM research_workflows ORDER BY rowid DESC'):
                    if project and row['rig_id'] != project:
                        continue
                    workflow = json.loads(row['spec_json'])
                    break
            body = {'resource_ids': (workflow or {}).get('resource_ids', []), 'workflow': workflow}
            con.execute('INSERT OR IGNORE INTO project_configuration VALUES(1,1,?)', (canonical(body),))
            con.commit()

    def get(self, project):
        self.projects.project(project)
        with self.projects.connection(project) as con:
            self.setup(con,project)
            row = con.execute('SELECT * FROM project_configuration').fetchone()
            body = json.loads(row['body_json'])
            run = body.get('run') or RunConfiguration.from_workflow(body.get('workflow')).model_dump(mode='json')
            body['run'] = run
            if body.get('workflow'):
                body['workflow'] = {**body['workflow'], **run}
            available = {r[0] for r in con.execute('SELECT id FROM resources WHERE id NOT IN (SELECT resource_id FROM source_deletions)')}
            body['resource_ids'] = [r for r in body['resource_ids'] if r in available]
            return {'version': row['version'], **body}

    def validate_sources(self, project, sources):
        if len(sources) > 30 or len(sources) != len(set(sources)):
            raise ValueError('Chọn tối đa 30 nguồn khác nhau')
        available = {r['id'] for r in self.projects.resources(project) if not r.get('deletion_pending')}
        if set(sources) - available:
            raise StoreConflict('Nguồn đã bị xóa hoặc không thuộc project này')

    def update(self, project, *, version=None, resource_ids=None, workflow=None):
        if resource_ids is not None:
            self.validate_sources(project, resource_ids)
        with self.projects.connection(project) as con:
            self.setup(con,project)
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM project_configuration').fetchone()
            if version is not None and row['version'] != version:
                raise StoreConflict('Cấu hình project đã thay đổi; tải lại trước khi lưu')
            body = json.loads(row['body_json'])
            if resource_ids is not None:
                body['resource_ids'] = resource_ids
            if workflow is not None:
                # Store orchestration separately. Older clients can seed the
                # run defaults once, but cannot overwrite Run-owned settings.
                body.setdefault('run',RunConfiguration.from_workflow(body.get('workflow') or workflow).model_dump(mode='json'))
                body['workflow'] = {k:v for k,v in workflow.items() if k not in RunConfiguration.model_fields}
            if canonical(body) != row['body_json']:
                con.execute('UPDATE project_configuration SET version=version+1,body_json=?', (canonical(body),))
        return self.get(project)

    def save_run(self, project, version, run):
        if run.benchmark_id:
            from .benchmarks import BenchmarkCatalog
            BenchmarkCatalog(self.projects).require(project,run.benchmark_id)
        with self.projects.connection(project) as con:
            self.setup(con,project)
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM project_configuration').fetchone()
            if row['version']!=version:
                raise StoreConflict('Cấu hình project đã thay đổi; tải lại trước khi lưu')
            body = json.loads(row['body_json'])
            body['run'] = run.model_dump(mode='json')
            if body.get('workflow'):
                body['workflow'] = {k:v for k,v in body['workflow'].items() if k not in RunConfiguration.model_fields}
            if canonical(body)!=row['body_json']:
                con.execute('UPDATE project_configuration SET version=version+1,body_json=?',(canonical(body),))
        return self.get(project)

    def workflow_spec(self, project, spec, version=None):
        """Compose current project defaults without mutating existing grants."""
        from .workflow_models import WorkflowSpec
        saved = self.get(project)
        if version is not None and saved['version']!=version:
            raise StoreConflict('Cấu hình Run hoặc Library đã đổi; tải lại Workflow trước khi lưu')
        return WorkflowSpec.model_validate({**spec.model_dump(mode='json'),**saved['run'],
            'resource_ids':saved['resource_ids']})

    def selection(self, project, idea):
        self.projects.idea(project, idea)
        defaults = self.get(project)
        with self.projects.connection(project) as con:
            self.setup(con,project)
            row = con.execute('SELECT * FROM idea_context WHERE idea_id=?', (idea,)).fetchone()
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='research_workflows'").fetchone():
                for flow in con.execute('SELECT spec_json,state_json FROM research_workflows ORDER BY rowid DESC'):
                    state = json.loads(flow['state_json'])
                    if state.get('idea_id')==idea and state['status']!='DONE':
                        return {'version':row['version'] if row else 0,'mode':'pinned','resource_ids':json.loads(flow['spec_json'])['resource_ids']}
            if row and row['resource_ids_json'] is not None:
                return {'version': row['version'], 'mode': 'custom', 'resource_ids': json.loads(row['resource_ids_json'])}
            # Historical proposals keep their exact source scope until explicitly reset.
            if row is None or row['resource_ids_json'] is None:
                proposal = con.execute('SELECT context_snapshot_json,state FROM proposals WHERE idea_id=? ORDER BY version DESC LIMIT 1', (idea,)).fetchone()
                if proposal and (row is None or proposal['state']!='STALE'):
                    sources = json.loads(proposal[0])['resources']
                    return {'version': row['version'] if row else 0, 'mode': 'pinned', 'resource_ids': [r['id'] for r in sources]}
            if row is None:
                variant = con.execute('SELECT variant_json FROM variant_ideas WHERE idea_id=?',(idea,)).fetchone()
                if variant:
                    sources = json.loads(variant[0])['baseline']['parent']['sources']
                    available = {r[0] for r in con.execute('SELECT id FROM resources WHERE id NOT IN (SELECT resource_id FROM source_deletions)')}
                    return {'version':0,'mode':'custom','resource_ids':[r['id'] for r in sources if r['id'] in available]}
        return {'version': row['version'] if row else 0, 'mode': 'inherit', 'resource_ids': defaults['resource_ids']}

    def select(self, project, idea, sources, version):
        self.projects.idea(project, idea)
        if sources is not None:
            self.validate_sources(project, sources)
        with self.projects.connection(project) as con:
            self.setup(con,project)
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM idea_context WHERE idea_id=?', (idea,)).fetchone()
            if (row['version'] if row else 0) != version:
                raise StoreConflict('Nguồn của idea đã thay đổi; tải lại trước khi lưu')
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='research_workflows'").fetchone():
                for flow in con.execute('SELECT state_json FROM research_workflows'):
                    state = json.loads(flow[0])
                    if state.get('idea_id') == idea and state['status'] in {'RUNNING','WAITING','UNKNOWN'}:
                        raise StoreConflict('Nguồn đã được ghim cho workflow đang chạy; dừng và tạo lượt mới để đổi nguồn')
            body = canonical(sources) if sources is not None else None
            con.execute('INSERT INTO idea_context VALUES(?,?,?) ON CONFLICT(idea_id) DO UPDATE SET version=excluded.version,resource_ids_json=excluded.resource_ids_json', (idea, version+1, body))
            con.execute("UPDATE proposals SET state='STALE' WHERE idea_id=? AND state IN ('AWAITING_APPROVAL','NEEDS_CLARIFICATION')", (idea,))
        return self.selection(project, idea)

    def idea_values(self, project, value):
        """Only omitted fields inherit; explicit empty/false choices are overrides."""
        saved = self.get(project)['run']
        body = value.model_dump()
        for field in ('mode','desired_output','benchmark_id','research'):
            if field not in value.model_fields_set and field in saved:
                body[field] = saved[field]
        if body['mode'] != 'training_research':
            body['research'] = None
            body['benchmark_id'] = None
        return body
