"""Durable Working lifecycle. Terminal states require proof that Kaggle stopped."""
from datetime import datetime, timezone
import json
import math
import re
import time

from .store import StoreConflict, canonical
from .modes import snapshot_settings
from .monitor_store import telemetry, node_telemetry

SCHEMA = '''CREATE TABLE IF NOT EXISTS working_runs(
run_id TEXT PRIMARY KEY REFERENCES runs(id), session_id TEXT NOT NULL UNIQUE,
phase TEXT NOT NULL, accelerator TEXT NOT NULL, ttl_seconds INTEGER NOT NULL,
started_at TEXT NOT NULL, descriptor_json TEXT, agent_called INTEGER NOT NULL DEFAULT 0,
outcome TEXT, summary_json TEXT, manifest_json TEXT, stop_json TEXT,
stop_confirmed INTEGER NOT NULL DEFAULT 0, account TEXT)'''
TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED'}
TELEMETRY_SCHEMA = '''CREATE TABLE IF NOT EXISTS working_telemetry(
run_id TEXT PRIMARY KEY REFERENCES runs(id), metric_lines_json TEXT NOT NULL DEFAULT '[]',
carry TEXT NOT NULL DEFAULT '', points_json TEXT NOT NULL DEFAULT '[]', error TEXT,
primary_metric TEXT, direction TEXT, gap INTEGER NOT NULL DEFAULT 0)'''
COLLECTOR_SCHEMA = '''CREATE TABLE IF NOT EXISTS working_collector_stats(
run_id TEXT PRIMARY KEY REFERENCES runs(id), upstream_frames INTEGER NOT NULL DEFAULT 0,
upstream_log_bytes INTEGER NOT NULL DEFAULT 0, client_reads INTEGER NOT NULL DEFAULT 0,
client_bytes INTEGER NOT NULL DEFAULT 0, client_latency_ms REAL NOT NULL DEFAULT 0)'''


class WorkingStore:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def _schema(connection):
        connection.execute(SCHEMA)
        connection.execute(TELEMETRY_SCHEMA)
        connection.execute(COLLECTOR_SCHEMA)
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(working_collector_stats)')}
        for column in ('provider_start_json', 'provider_end_json'):
            if column not in columns:
                connection.execute(f'ALTER TABLE working_collector_stats ADD COLUMN {column} TEXT')
        if 'gap' not in {row['name'] for row in connection.execute('PRAGMA table_info(working_telemetry)')}:
            connection.execute('ALTER TABLE working_telemetry ADD COLUMN gap INTEGER NOT NULL DEFAULT 0')
        if 'account' not in {row['name'] for row in connection.execute('PRAGMA table_info(working_runs)')}:
            connection.execute('ALTER TABLE working_runs ADD COLUMN account TEXT')

    def get(self, project_id, run_id):
        self.store.run(project_id, run_id)
        with self.store.connection(project_id) as connection:
            self._schema(connection)
            row = connection.execute('SELECT * FROM working_runs WHERE run_id=?', (run_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            for name in ('descriptor', 'summary', 'manifest', 'stop'):
                raw = result.pop(name + '_json')
                result[name] = json.loads(raw) if raw else None
            result['account'] = result['account'] or (result['descriptor'] or {}).get('account')
            result['stop_confirmed'] = bool(result['stop_confirmed'])
            return result

    def reserve(self, project_id, run_id, accelerator, ttl, account=None, queued=False):
        with self.store.connection(project_id) as connection:
            self._schema(connection)
            connection.execute('BEGIN IMMEDIATE')
            if connection.execute('SELECT 1 FROM working_runs WHERE run_id=?', (run_id,)).fetchone():
                raise StoreConflict('Working đã được yêu cầu cho Run này; kết nối lại, không gửi notebook mới')
            run = connection.execute('SELECT runs.*,proposals.state AS proposal_state FROM runs JOIN proposals ON proposals.id=runs.proposal_id WHERE runs.id=?', (run_id,)).fetchone()
            if run is None:
                raise KeyError('Run not found')
            if run['deleted_at'] or run['proposal_state'] != 'APPROVED' or run['state'] not in {'APPROVED', 'PREFLIGHT', 'FAILED'} or run['identity_json']:
                raise StoreConflict('Working requires an approved, unsubmitted Run')
            connection.execute('INSERT INTO working_runs(run_id,session_id,phase,accelerator,ttl_seconds,started_at,account) VALUES(?,?,?,?,?,?,?)',
                               (run_id, run_id, 'queued' if queued else 'starting', accelerator, ttl,
                                datetime.now(timezone.utc).isoformat(), account))
            approved = connection.execute('SELECT proposals.body_json FROM proposals JOIN runs ON runs.proposal_id=proposals.id WHERE runs.id=?',
                                          (run_id,)).fetchone()
            metric = json.loads(approved[0]).get('metric') if approved else None
            name = metric.get('name') if isinstance(metric, dict) else None
            direction = metric.get('direction') if isinstance(metric, dict) else None
            connection.execute('INSERT INTO working_telemetry(run_id,primary_metric,direction) VALUES(?,?,?)',
                               (run_id, name, direction))
            connection.execute('INSERT INTO working_collector_stats(run_id) VALUES(?)', (run_id,))
            connection.execute('UPDATE runs SET state=?,error=NULL WHERE id=?',
                               ('QUEUED' if queued else 'STARTING', run_id))

    def update(self, project_id, run_id, *, state=None, error=None, **values):
        allowed = {'phase', 'descriptor', 'agent_called', 'outcome', 'summary', 'manifest', 'stop'}
        if not set(values).issubset(allowed) or state in TERMINAL:
            raise ValueError('Terminal Working states must use finish() with a stop receipt')
        with self.store.connection(project_id) as connection:
            self._schema(connection)
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
            approved = connection.execute('SELECT context_snapshot_json,body_json FROM proposals JOIN runs ON runs.proposal_id=proposals.id WHERE runs.id=?', (run_id,)).fetchone()
            snapshot = json.loads(approved['context_snapshot_json'])
            mode, _ = snapshot_settings(snapshot)
            research = json.loads(approved['body_json']).get('research') or {}
            report_requested = research.get('report', snapshot['idea'].get('run_model') != 'single')
            if mode in {'etc', 'benchmark'} and report_path is not None:
                raise StoreConflict('Etc saves Output instead of a research report')
            if outcome == 'COMPLETED' and (not record['summary_json'] or not record['manifest_json']
                    or (mode == 'training_research' and report_requested and report_path != 'report.md')):
                raise StoreConflict('Working outputs or selected report are not durable')
            if outcome == 'COMPLETED' and mode in {'etc', 'benchmark'} and json.loads(record['manifest_json']).get('complete') is not True:
                raise StoreConflict('Etc output collection is incomplete')
            if outcome == 'COMPLETED' and json.loads(record['summary_json']).get('succeeded') is not True:
                raise StoreConflict('The agent did not report successful work')
            if record['stop_confirmed']:
                return
            connection.execute("UPDATE working_runs SET phase='stopped',outcome=?,stop_json=?,stop_confirmed=1 WHERE run_id=?", (outcome, canonical(receipt), run_id))
            connection.execute('UPDATE runs SET state=?,report_path=?,error=NULL WHERE id=?', (outcome, report_path, run_id))

    def append_log(self, project_id, run_id, text, stream='stdout'):
        with self.store.connection(project_id) as connection:
            self._schema(connection)
            connection.execute('BEGIN IMMEDIATE')
            if stream != 'backend':
                connection.execute('INSERT OR IGNORE INTO working_collector_stats(run_id) VALUES(?)', (run_id,))
                connection.execute('UPDATE working_collector_stats SET upstream_frames=upstream_frames+1,upstream_log_bytes=upstream_log_bytes+? WHERE run_id=?',
                                   (len(text.encode('utf-8')), run_id))
            total = connection.execute('SELECT COALESCE(SUM(length(text)),0) FROM logs WHERE run_id=?', (run_id,)).fetchone()[0]
            if total >= 2_000_000:
                connection.execute('UPDATE working_telemetry SET gap=1 WHERE run_id=?', (run_id,))
                return
            seq = connection.execute('SELECT COALESCE(MAX(seq),0)+1 FROM logs WHERE run_id=? AND generation=1', (run_id,)).fetchone()[0]
            clipped = text[:max(0, 2_000_000-total)]
            connection.execute('INSERT INTO logs VALUES(?,1,?,?,?)', (run_id, seq, clipped, stream))
            if len(clipped) < len(text):
                connection.execute('UPDATE working_telemetry SET gap=1 WHERE run_id=?', (run_id,))
            state = connection.execute('SELECT * FROM working_telemetry WHERE run_id=?', (run_id,)).fetchone()
            if stream != 'backend' and state and state['primary_metric']:
                combined = state['carry'] + clipped
                lines = combined.split('\n')
                carry = lines.pop()
                metric_lines = json.loads(state['metric_lines_json'])
                metric_lines.extend(line.rstrip('\r') for line in lines if line.startswith('AILAB_METRIC '))
                if len(carry) > 16_384 or len(metric_lines) > 1000:
                    carry = ''
                    metric_lines = metric_lines[-1000:]
                    error = 'Metric stream vượt giới hạn; xem log gốc.'
                else:
                    error = None
                points, parsed_error = telemetry([{'data': line} for line in metric_lines], state['primary_metric'], max_steps=1_000_000)
                connection.execute('UPDATE working_telemetry SET carry=?,metric_lines_json=?,points_json=?,error=? WHERE run_id=?',
                                   (carry, canonical(metric_lines), canonical(points), error or parsed_error, run_id))

    def logs(self, project_id, run_id, cursor=None, limit=100):
        if not 1 <= limit <= 250 or (cursor and not re.fullmatch(r'1:[0-9]{1,10}', cursor)):
            raise ValueError('Invalid log cursor or page limit')
        seq = int(cursor.split(':')[1]) if cursor else 0
        run = self.store.run(project_id, run_id)
        state_path=self.store.run_root(project_id,run_id)/'logs/0-run/search-state.json'
        with self.store.connection(project_id) as connection:
            rows = connection.execute('SELECT seq,text,stream FROM logs WHERE run_id=? AND generation=1 AND seq>? ORDER BY seq LIMIT ?', (run_id, seq, limit + 1)).fetchall()
            count = connection.execute('SELECT COALESCE(MAX(seq),0) FROM logs WHERE run_id=? AND generation=1', (run_id,)).fetchone()[0]
            self._schema(connection)
            telemetry_row = connection.execute('SELECT * FROM working_telemetry WHERE run_id=?', (run_id,)).fetchone()
            node_records=(connection.execute('SELECT text,stream FROM logs WHERE run_id=? AND generation=1 ORDER BY seq',(run_id,)).fetchall()
                          if state_path.is_file() else [])
        if seq > count:
            raise ValueError('Log cursor is ahead of stored records')
        entries = [dict(row) for row in rows[:limit]]
        points = json.loads(telemetry_row['points_json']) if telemetry_row else []
        segmented=None
        if telemetry_row and telemetry_row['primary_metric']:
            selected=None
            if run['state'] in TERMINAL and state_path.is_file():
                selected=json.loads(state_path.read_text(encoding='utf-8')).get('selected_node_id')
            segmented=node_telemetry(node_records,telemetry_row['primary_metric'],selected)
            if segmented:points=segmented['points']
        telemetry_error=segmented['error'] if segmented else telemetry_row['error'] if telemetry_row else None
        eta = None
        if (run['state'] not in TERMINAL and telemetry_row and not telemetry_error and not telemetry_row['gap'] and len(points) >= 2):
            previous, latest = points[-2:]
            duration = latest['elapsed_seconds'] - previous['elapsed_seconds']
            steps = latest['step'] - previous['step']
            if duration > 0 and steps > 0 and latest['step'] < latest['total_steps']:
                estimate = duration / steps * (latest['total_steps'] - latest['step'])
                if math.isfinite(estimate):
                    eta = estimate
        return {'run_state': run['state'], 'entries': entries, 'generation': 1,
                'next_cursor': '1:' + str(entries[-1]['seq'] if entries else seq), 'has_more': len(rows) > limit,
                'terminal': run['state'] in TERMINAL, 'reset': False,
                'gap': bool(telemetry_row and telemetry_row['gap']),
                'error': run['error'], 'telemetry_error': telemetry_error,
                'metric_nodes':segmented['nodes'] if segmented else [],'metric_node':segmented['node'] if segmented else None,
                'points': points, 'eta_seconds': eta,
                'primary_metric': telemetry_row['primary_metric'] if telemetry_row else None,
                'direction': telemetry_row['direction'] if telemetry_row else None, 'observation': None}

    def result_metric(self, project_id, run_id):
        page = self.logs(project_id, run_id, limit=1)
        points, name, direction = page['points'], page['primary_metric'], page['direction']
        if (page['run_state'] != 'COMPLETED' or page['gap'] or page['telemetry_error'] or not points
                or direction not in {'minimize', 'maximize'} or points[-1]['step'] != points[-1]['total_steps']):
            return None
        values = [point['metrics'][name] for point in points]
        return {'name': name, 'direction': direction, 'final_value': values[-1],
                'best_value': (min if direction == 'minimize' else max)(values), 'source': 'ssh_telemetry'}

    def client_read(self, project_id, run_id, payload, started_at):
        size = len(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        latency_ms = max(0, (time.perf_counter() - started_at) * 1000)
        with self.store.connection(project_id) as connection:
            self._schema(connection)
            connection.execute('INSERT OR IGNORE INTO working_collector_stats(run_id) VALUES(?)', (run_id,))
            connection.execute('UPDATE working_collector_stats SET client_reads=client_reads+1,client_bytes=client_bytes+?,client_latency_ms=client_latency_ms+? WHERE run_id=?',
                               (size, latency_ms, run_id))

    def snapshot_provider(self, project_id, run_id, snapshot, *, end=False):
        with self.store.connection(project_id) as connection:
            self._schema(connection)
            column = 'provider_end_json' if end else 'provider_start_json'
            connection.execute(f'UPDATE working_collector_stats SET {column}=? WHERE run_id=?',
                               (canonical(snapshot), run_id))

    def collector_stats(self, project_id, run_id, current=None):
        self.store.run(project_id, run_id)
        with self.store.connection(project_id) as connection:
            self._schema(connection)
            row = connection.execute('SELECT * FROM working_collector_stats WHERE run_id=?', (run_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        start = json.loads(result.pop('provider_start_json') or 'null')
        end = json.loads(result.pop('provider_end_json') or 'null') or current
        provider = None
        if start and end and start['epoch'] == end['epoch']:
            fields = ('requests', 'request_bytes', 'response_bytes', 'latency_ms', 'errors')
            if all(end[key] >= start[key] for key in fields):
                provider = {key: end[key]-start[key] for key in fields}
                provider['mean_latency_ms'] = provider['latency_ms']/provider['requests'] if provider['requests'] else None
        result['provider'] = provider
        result['provider_scope'] = 'Kaggle SDK proxy, cookie API and notebook status payloads; excludes browser/login, SSH, headers and TLS; account window'
        result['client_mean_latency_ms'] = result['client_latency_ms'] / result['client_reads'] if result['client_reads'] else None
        return result
