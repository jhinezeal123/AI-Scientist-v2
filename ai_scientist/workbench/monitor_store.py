"""Persist replay positions, local cursors and measured telemetry in project SQLite."""
import json
import math
import re
from .store import canonical

SCHEMA = '''CREATE TABLE IF NOT EXISTS monitor_state(
run_id TEXT PRIMARY KEY REFERENCES runs(id), generation INTEGER NOT NULL DEFAULT 1,
snapshot_json TEXT NOT NULL DEFAULT '[]', points_json TEXT NOT NULL DEFAULT '[]',
gap INTEGER NOT NULL DEFAULT 0, terminal INTEGER NOT NULL DEFAULT 0,
observation_json TEXT, error TEXT, telemetry_error TEXT, primary_metric TEXT, direction TEXT)'''


def telemetry(records, metric, max_steps=100):
    points=[];error=None
    for record in records:
        for line in record['data'].splitlines():
            if not line.startswith('AILAB_METRIC '):continue
            try:
                item=json.loads(line[len('AILAB_METRIC '):])
                step=item['step'];elapsed=item['elapsed_seconds'];total=item['total_steps'];values=item['metrics']
                if (type(step) is not int or type(total) is not int or not 1<=step<=total<=max_steps
                        or type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed<0
                        or not isinstance(values,dict) or metric not in values or len(values)>32
                        or any(not isinstance(k,str) or len(k)>256 or type(v) not in (int,float) or not math.isfinite(v) for k,v in values.items())):
                    raise ValueError('Invalid telemetry')
                point={'step':step,'elapsed_seconds':elapsed,'total_steps':total,'metrics':values}
                if points and step==points[-1]['step'] and point==points[-1]:continue
                if points and (step<=points[-1]['step'] or elapsed<points[-1]['elapsed_seconds'] or total!=points[-1]['total_steps']):
                    raise ValueError('Conflicting telemetry sequence')
                points.append(point)
            except (ValueError,KeyError,TypeError,OverflowError):
                error='Có telemetry không hợp lệ; vẫn giữ nguyên log và chỉ lưu các mẫu xác minh được.'
    return points,error


def node_telemetry(records, metric, selected_node=None):
    """Separate step counters only at backend-authored experiment boundaries."""
    groups={};current=None
    for record in records:
        text=record['text']
        marker=(re.fullmatch(r'Giai đoạn ([1-4]_[A-Za-z0-9_-]+): (?:draft|improve|debug|seed) · node ([0-9a-f]{8,32})\n',text)
                if record['stream']=='backend' else None)
        if marker:
            stage,identity=marker.groups()
            current=groups.setdefault(identity,{'id':identity,'stage':stage,'chunks':[]})
        elif current is not None and record['stream']!='backend':
            current['chunks'].append(text)
    if not groups:return None
    nodes=[]
    for group in groups.values():
        split_lines=''.join(group.pop('chunks')).split('\n')
        carry=split_lines.pop()
        lines=split_lines
        metric_lines=[line.rstrip('\r') for line in lines if line.startswith('AILAB_METRIC ')]
        points,error=telemetry([{'data':line} for line in metric_lines[:1000]],metric,max_steps=1_000_000)
        nodes.append({**group,'points':points,'error':error or ('Metric stream vượt giới hạn; xem log gốc.' if len(metric_lines)>1000 or len(carry)>16384 else None)})
    chosen=nodes[-1]
    if selected_node:
        matches=[node for node in nodes if selected_node.startswith(node['id'])]
        if len(matches)!=1:return {'nodes':nodes,'points':[],'node':None,'error':'Không xác định được telemetry của node đã chọn.'}
        chosen=matches[0]
    return {'nodes':nodes,'points':chosen['points'],'node':chosen['id'],
            'error':next((node['error'] for node in nodes if node['error']),None)}


class MonitorStore:
    def __init__(self, store):self.store=store

    def ensure(self, connection, run_id):
        if connection.execute('SELECT 1 FROM runs WHERE id=?',(run_id,)).fetchone() is None:
            raise KeyError('Run not found')
        connection.execute(SCHEMA)

    def merge(self, project_id, run_id, snapshot, metric, direction):
        records=snapshot['records']
        with self.store.connection(project_id) as connection:
            self.ensure(connection,run_id)
            connection.execute('INSERT OR IGNORE INTO monitor_state(run_id) VALUES(?)',(run_id,))
            old=connection.execute('SELECT * FROM monitor_state WHERE run_id=?',(run_id,)).fetchone()
            previous=json.loads(old['snapshot_json']);generation=old['generation'];gap=bool(old['gap'])
            prefix=records[:len(previous)]==previous
            short=len(records)<len(previous) and previous[:len(records)]==records
            if snapshot['complete']:
                if records!=previous and not prefix:generation+=1
                current=records;gap=False
            elif short:
                current=previous
            elif prefix:
                current=records
            else:
                generation+=1;current=records;gap=True
            if snapshot.get('truncated'):gap=True
            count=connection.execute('SELECT COUNT(*) FROM logs WHERE run_id=? AND generation=?',(run_id,generation)).fetchone()[0]
            for index,record in enumerate(current[count:],count+1):
                connection.execute('INSERT INTO logs(run_id,generation,seq,text,stream) VALUES(?,?,?,?,?)',
                                   (run_id,generation,index,record['data'],record['stream_name']))
            points,telemetry_error=telemetry(current,metric)
            terminal=bool(snapshot['terminal'] and snapshot['complete'] and not gap)
            observation={key:snapshot[key] for key in ('identity','observed_at','source','complete','terminal')}
            connection.execute('UPDATE monitor_state SET generation=?,snapshot_json=?,points_json=?,gap=?,terminal=?,observation_json=?,error=NULL,telemetry_error=?,primary_metric=?,direction=? WHERE run_id=?',
                               (generation,canonical(current),canonical(points),int(gap),int(terminal),canonical(observation),telemetry_error,metric,direction,run_id))

    def failed_read(self, project_id, run_id, error):
        with self.store.connection(project_id) as connection:
            self.ensure(connection,run_id)
            connection.execute('INSERT OR IGNORE INTO monitor_state(run_id) VALUES(?)',(run_id,))
            connection.execute('UPDATE monitor_state SET error=? WHERE run_id=?',(error,run_id))

    def completed_snapshot(self, project_id, run_id):
        """Return the persisted full terminal records needed to resume T08 after restart."""
        with self.store.connection(project_id) as connection:
            self.ensure(connection,run_id)
            row=connection.execute('SELECT snapshot_json,gap,terminal,observation_json,telemetry_error FROM monitor_state WHERE run_id=?',(run_id,)).fetchone()
            if row is None or not row['terminal'] or row['gap']:
                return None
            observation=json.loads(row['observation_json']) if row['observation_json'] else None
            records=json.loads(row['snapshot_json'])
            if (not observation or observation.get('complete') is not True or observation.get('terminal') is not True
                    or not isinstance(records,list)):
                return None
            return {**observation,'records':records,'gap':bool(row['gap']),
                    'telemetry_error':row['telemetry_error']}

    def delta(self, project_id, run_id, cursor=None, limit=100):
        if type(limit) is not int or not 1<=limit<=250:raise ValueError('Log page limit must be 1..250')
        if cursor is not None and not re.fullmatch(r'[0-9]{1,10}:[0-9]{1,10}',cursor):raise ValueError('Invalid log cursor')
        with self.store.connection(project_id) as connection:
            self.ensure(connection,run_id)
            row=connection.execute('SELECT * FROM monitor_state WHERE run_id=?',(run_id,)).fetchone()
            generation=row['generation'] if row else 1
            client_generation,seq=map(int,cursor.split(':')) if cursor else (generation,0)
            reset=client_generation!=generation
            if reset:seq=0
            count=connection.execute('SELECT COUNT(*) FROM logs WHERE run_id=? AND generation=?',(run_id,generation)).fetchone()[0]
            if not reset and seq>count:raise ValueError('Log cursor is ahead of stored records')
            entries=[];size=0
            for item in connection.execute('SELECT seq,text,stream FROM logs WHERE run_id=? AND generation=? AND seq>? ORDER BY seq LIMIT ?', (run_id,generation,seq,limit)):
                length=len(item['text'].encode('utf-8'))
                if entries and size+length>128000:break
                size+=length;entries.append(dict(item))
            next_seq=entries[-1]['seq'] if entries else seq
            points=json.loads(row['points_json']) if row else []
            eta=None
            if row and not row['terminal'] and not row['gap'] and not row['error'] and not row['telemetry_error'] and len(points)>=2:
                first,last=points[-2:];duration=last['elapsed_seconds']-first['elapsed_seconds']
                if duration>0 and last['step']<last['total_steps']:
                    eta=duration/(last['step']-first['step'])*(last['total_steps']-last['step'])
            run_state=connection.execute('SELECT state FROM runs WHERE id=?',(run_id,)).fetchone()[0]
            return {'run_state':run_state,'generation':generation,'entries':entries,'next_cursor':f'{generation}:{next_seq}',
                    'has_more':next_seq<count,'reset':reset,'gap':bool(row and row['gap']),
                    'terminal':bool(row and row['terminal']),'points':points,'eta_seconds':eta,
                    'observation':json.loads(row['observation_json']) if row and row['observation_json'] else None,
                    'error':row['error'] if row else None,'telemetry_error':row['telemetry_error'] if row else None,
                    'primary_metric':row['primary_metric'] if row else None,'direction':row['direction'] if row else None}
