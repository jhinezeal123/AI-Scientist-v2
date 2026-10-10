"""Workflow intent and human inputs live alongside authoritative project runs."""
import json
import uuid
from datetime import datetime, timezone
from .store import StoreConflict
from .workflow_models import WorkflowSpec

def now():
    return datetime.now(timezone.utc).isoformat()

class WorkflowStore:
    def __init__(self, projects):
        self.projects = projects

    def setup(self, con):
        con.execute('CREATE TABLE IF NOT EXISTS research_workflows(id TEXT PRIMARY KEY,rig_id TEXT NOT NULL,spec_json TEXT NOT NULL,state_json TEXT NOT NULL,updated_at TEXT NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS workflow_inputs(id TEXT PRIMARY KEY,workflow_id TEXT NOT NULL,stage TEXT NOT NULL,prompt_json TEXT NOT NULL,result_json TEXT,state TEXT NOT NULL,created_at TEXT NOT NULL)')

    def list(self, project, rig):
        with self.projects.connection(project) as con:
            self.setup(con)
            return [self.decode(row) for row in con.execute('SELECT * FROM research_workflows WHERE rig_id=? ORDER BY rowid DESC', (rig,))]

    @staticmethod
    def decode(row):
        return {'id': row['id'], 'rig_id': row['rig_id'], 'spec': json.loads(row['spec_json']),
                'state': json.loads(row['state_json']), 'updated_at': row['updated_at']}

    def get(self, project, identity):
        with self.projects.connection(project) as con:
            self.setup(con)
            row = con.execute('SELECT * FROM research_workflows WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise KeyError('Workflow not found')
            return self.decode(row)

    def create(self, project, rig, identity, spec, source_fingerprints=None):
        with self.projects.connection(project) as con:
            self.setup(con)
            con.execute('BEGIN IMMEDIATE')
            existing = con.execute('SELECT * FROM research_workflows WHERE id=?', (identity,)).fetchone()
            body = spec.model_dump(mode='json')
            if existing:
                if existing['rig_id'] != rig or json.loads(existing['spec_json']) != body:
                    raise StoreConflict('Workflow request ID belongs to different configuration')
                return self.decode(existing)
            state = {'status': 'PAUSED', 'stage': 'ideation', 'iteration': 0, 'calls': 0,
                     'runs': [], 'idea_id': None, 'proposal_id': None, 'run_id': None,
                     'events': [], 'grant_id': uuid.uuid4().hex, 'approvals': [], 'generation': 0,
                     'source_fingerprints': source_fingerprints or {}}
            con.execute('INSERT INTO research_workflows VALUES(?,?,?,?,?)',
                        (identity, rig, json.dumps(body), json.dumps(state), now()))
        return self.get(project, identity)

    def change(self, project, identity, operation):
        with self.projects.connection(project) as con:
            self.setup(con)
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM research_workflows WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise KeyError('Workflow not found')
            state = json.loads(row['state_json'])
            operation(state)
            con.execute('UPDATE research_workflows SET state_json=?,updated_at=? WHERE id=?',
                        (json.dumps(state), now(), identity))
        return self.get(project, identity)

    def event(self, project, identity, stage, kind, **details):
        def add(state):
            state['stage'] = stage
            state['events'] = (state['events'] + [{'stage': stage, 'kind': kind, 'at': now(), **details}])[-200:]
        return self.change(project, identity, add)

    def reserve_call(self, project, identity):
        allocated = []
        spec = WorkflowSpec.model_validate(self.get(project, identity)['spec'])
        def reserve(state):
            if state['status'] not in {'RUNNING', 'WAITING'}:
                raise StoreConflict('Workflow is paused')
            if state['calls'] >= spec.max_agent_calls:
                raise StoreConflict('Operator agent-call budget exhausted')
            state['calls'] += 1
            allocated.append(state['calls'])
        self.change(project, identity, reserve)
        return allocated[0]

    def input(self, project, identity, stage, prompt):
        input_id = uuid.uuid4().hex
        with self.projects.connection(project) as con:
            self.setup(con)
            con.execute('BEGIN IMMEDIATE')
            workflow = con.execute('SELECT state_json FROM research_workflows WHERE id=?', (identity,)).fetchone()
            state = json.loads(workflow['state_json'])
            if state['status'] not in {'RUNNING','WAITING'}:
                raise StoreConflict('Workflow is paused')
            prompt = {**prompt, 'iteration': state['iteration']}
            existing = next((row for row in con.execute('SELECT * FROM workflow_inputs WHERE workflow_id=? AND stage=? ORDER BY rowid DESC', (identity,stage))
                             if json.loads(row['prompt_json']) == prompt), None)
            if existing:
                input_id = existing['id']
                if existing['state'] == 'DONE':
                    return input_id
            else:
                con.execute('INSERT INTO workflow_inputs VALUES(?,?,?,?,NULL,?,?)',
                            (input_id, identity, stage, json.dumps(prompt), 'PENDING', now()))
            state.update(status='WAITING',stage=stage)
            state['events'] = (state['events'] + [{'stage':stage,'kind':'waiting_for_human','at':now(),'input_id':input_id}])[-200:]
            con.execute('UPDATE research_workflows SET state_json=?,updated_at=? WHERE id=?', (json.dumps(state),now(),identity))
        return input_id

    def inputs(self, project, identity):
        with self.projects.connection(project) as con:
            self.setup(con)
            return [{**dict(row), 'prompt': json.loads(row['prompt_json']),
                     'result': json.loads(row['result_json']) if row['result_json'] else None}
                    for row in con.execute('SELECT * FROM workflow_inputs WHERE workflow_id=? ORDER BY rowid DESC', (identity,))]

    def answer(self, project, identity, input_id, result):
        with self.projects.connection(project) as con:
            self.setup(con)
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM workflow_inputs WHERE id=? AND workflow_id=?', (input_id, identity)).fetchone()
            if row is None:
                raise KeyError('Human input not found')
            if row['state'] != 'PENDING':
                if json.loads(row['result_json']) != result:
                    raise StoreConflict('Human response already committed')
                return
            workflow = con.execute('SELECT state_json FROM research_workflows WHERE id=?', (identity,)).fetchone()
            state = json.loads(workflow['state_json'])
            if state['status'] != 'WAITING':
                raise StoreConflict('Resume the paused workflow before answering')
            prompt = json.loads(row['prompt_json'])
            import jsonschema
            schema = ({'type':'object','required':['approve','reason'],'properties':{
                'approve':{'type':'boolean'},'reason':{'type':'string','minLength':1}},'additionalProperties':False}
                if prompt['kind']=='review' else prompt['schema'])
            try:
                jsonschema.validate(result, schema)
            except jsonschema.ValidationError:
                raise ValueError('Human response does not match this stage result schema') from None
            if len(json.dumps(result).encode()) > 60000:
                raise ValueError('Human stage result exceeds 60KB')
            con.execute("UPDATE workflow_inputs SET state='DONE',result_json=? WHERE id=?", (json.dumps(result), input_id))
            state['status']='RUNNING'
            con.execute('UPDATE research_workflows SET state_json=?,updated_at=? WHERE id=?', (json.dumps(state),now(),identity))
