"""Durable Working lifecycle. Terminal states require proof that Kaggle stopped."""
from datetime import datetime, timezone
import json
import re

from .store import StoreConflict, canonical

SCHEMA = '''CREATE TABLE IF NOT EXISTS working_runs(
run_id TEXT PRIMARY KEY REFERENCES runs(id), session_id TEXT NOT NULL UNIQUE,
phase TEXT NOT NULL, accelerator TEXT NOT NULL, ttl_seconds INTEGER NOT NULL,
started_at TEXT NOT NULL, descriptor_json TEXT, agent_called INTEGER NOT NULL DEFAULT 0,
outcome TEXT, summary_json TEXT, manifest_json TEXT, stop_json TEXT,
stop_confirmed INTEGER NOT NULL DEFAULT 0)'''
TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED'}


class WorkingStore:
    def __init__(self, store):
        self.store = store

    def get(self, project_id, run_id):
        self.store.run(project_id, run_id)
        with self.store.connection(project_id) as connection:
            connection.execute(SCHEMA)
            row = connection.execute('SELECT * FROM working_runs WHERE run_id=?', (run_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            for name in ('descriptor', 'summary', 'manifest', 'stop'):
                raw = result.pop(name + '_json')
                result[name] = json.loads(raw) if raw else None
            result['stop_confirmed'] = bool(result['stop_confirmed'])
            return result

    def reserve(self, project_id, run_id, accelerator, ttl):
        with self.store.connection(project_id) as connection:
            connection.execute(SCHEMA)
            connection.execute('BEGIN IMMEDIATE')
            if connection.execute('SELECT 1 FROM working_runs WHERE run_id=?', (run_id,)).fetchone():
                raise StoreConflict('Working đã được yêu cầu cho Run này; kết nối lại, không gửi notebook mới')
            run = connection.execute('SELECT runs.*,proposals.state AS proposal_state FROM runs JOIN proposals ON proposals.id=runs.proposal_id WHERE runs.id=?', (run_id,)).fetchone()
            if run is None:
                raise KeyError('Run not found')
            if run['proposal_state'] != 'APPROVED' or run['state'] not in {'APPROVED', 'PREFLIGHT', 'FAILED'} or run['identity_json']:
                raise StoreConflict('Working requires an approved, unsubmitted Run')
            connection.execute('INSERT INTO working_runs(run_id,session_id,phase,accelerator,ttl_seconds,started_at) VALUES(?,?,?,?,?,?)',
                               (run_id, run_id, 'starting', accelerator, ttl, datetime.now(timezone.utc).isoformat()))
            connection.execute("UPDATE runs SET state='STARTING',error=NULL WHERE id=?", (run_id,))

    def update(self, project_id, run_id, *, state=None, error=None, **values):
        allowed = {'phase', 'descriptor', 'agent_called', 'outcome', 'summary', 'manifest', 'stop'}
        if not set(values).issubset(allowed) or state in TERMINAL:
            raise ValueError('Terminal Working states must use finish() with a stop receipt')
        with self.store.connection(project_id) as connection:
            connection.execute(SCHEMA)
            connection.execute('BEGIN IMMEDIATE')
            record = connection.execute('SELECT stop_confirmed FROM working_runs WHERE run_id=?', (run_id,)).fetchone()
            if record is None:
                raise KeyError('Working run not found')
            if record['stop_confirmed']:
                raise StoreConflict('Working is already stopped')
            for key, value in values.items():
                column = key + '_json' if key in {'descriptor', 'summary', 'manifest', 'stop'} else key
                if column.endswith('_json'):
                    value = canonical(value)
                connection.execute(f'UPDATE working_runs SET {column}=? WHERE run_id=?', (value, run_id))
            if state:
                connection.execute('UPDATE runs SET state=?,error=? WHERE id=?', (state, error, run_id))

    def finish(self, project_id, run_id, receipt, outcome, report_path=None):
        if outcome not in TERMINAL or receipt.get('stopped') is not True or receipt.get('session_id') != run_id:
            raise StoreConflict('Kaggle stop has not been confirmed for this Run')
        with self.store.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            record = connection.execute('SELECT * FROM working_runs WHERE run_id=?', (run_id,)).fetchone()
            if record is None:
                raise KeyError('Working run not found')
            descriptor = json.loads(record['descriptor_json']) if record['descriptor_json'] else None
            if descriptor and receipt.get('notebook_ref') != descriptor['notebook_ref']:
                raise StoreConflict('Stop receipt belongs to a different Kaggle notebook')
            if outcome == 'COMPLETED' and (not record['summary_json'] or not record['manifest_json'] or report_path != 'report.md'):
                raise StoreConflict('Working outputs and report are not durable')
            if outcome == 'COMPLETED' and json.loads(record['summary_json']).get('succeeded') is not True:
                raise StoreConflict('The agent did not report successful work')
            if record['stop_confirmed']:
                return
            connection.execute("UPDATE working_runs SET phase='stopped',outcome=?,stop_json=?,stop_confirmed=1 WHERE run_id=?", (outcome, canonical(receipt), run_id))
            connection.execute('UPDATE runs SET state=?,report_path=?,error=NULL WHERE id=?', (outcome, report_path, run_id))

    def append_log(self, project_id, run_id, text, stream='stdout'):
        with self.store.connection(project_id) as connection:
            connection.execute('BEGIN IMMEDIATE')
            total = connection.execute('SELECT COALESCE(SUM(length(text)),0) FROM logs WHERE run_id=?', (run_id,)).fetchone()[0]
            if total >= 2_000_000:
                return
            seq = connection.execute('SELECT COALESCE(MAX(seq),0)+1 FROM logs WHERE run_id=? AND generation=1', (run_id,)).fetchone()[0]
            connection.execute('INSERT INTO logs VALUES(?,1,?,?,?)', (run_id, seq, text[:max(0, 2_000_000-total)], stream))

    def logs(self, project_id, run_id, cursor=None, limit=100):
        if not 1 <= limit <= 250 or (cursor and not re.fullmatch(r'1:[0-9]{1,10}', cursor)):
            raise ValueError('Invalid log cursor or page limit')
        seq = int(cursor.split(':')[1]) if cursor else 0
        run = self.store.run(project_id, run_id)
        with self.store.connection(project_id) as connection:
            rows = connection.execute('SELECT seq,text,stream FROM logs WHERE run_id=? AND generation=1 AND seq>? ORDER BY seq LIMIT ?', (run_id, seq, limit + 1)).fetchall()
        entries = [dict(row) for row in rows[:limit]]
        return {'run_state': run['state'], 'entries': entries, 'generation': 1,
                'next_cursor': '1:' + str(entries[-1]['seq'] if entries else seq), 'has_more': len(rows) > limit,
                'terminal': run['state'] in TERMINAL, 'reset': False, 'gap': False,
                'error': run['error'], 'telemetry_error': None, 'points': [], 'primary_metric': None,
                'direction': None, 'observation': None}
