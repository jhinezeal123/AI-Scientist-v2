"""Explicit local resource inventory and opt-in integration configuration."""
from __future__ import annotations

import json
from urllib import request as urllib_request

from .store import _json
from .models import StrictModel
from pydantic import Field


class CodingResource(StrictModel):
    id: str = Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')
    name: str = Field(min_length=1,max_length=120)
    seat_ids: list[str] = Field(min_length=1,max_length=32)
    max_parallel: int = Field(ge=1,le=32)


def resource_limits(store,rig_id):
    with store.connect() as con:
        return [CodingResource.model_validate_json(row[0]) for row in con.execute('SELECT spec_json FROM resources WHERE rig_id=? ORDER BY id',(rig_id,))]


def configure_resource(store,rig_id,resource):
    with store.connect(True) as con:
        runtime=con.execute('SELECT enabled FROM rig_runtime WHERE rig_id=?',(rig_id,)).fetchone()
        if not runtime:
            raise KeyError(rig_id)
        if runtime['enabled'] or con.execute("SELECT 1 FROM seats WHERE rig_id=? AND state IN ('BUSY','UNKNOWN')",(rig_id,)).fetchone():
            raise ValueError('Pause and reconcile the team before changing resources')
        seats={s.id for s in store.rig(rig_id).seats}
        if len(set(resource.seat_ids))!=len(resource.seat_ids) or set(resource.seat_ids)-seats:
            raise ValueError('Resource must reference distinct configured seats')
        con.execute('INSERT OR REPLACE INTO resources VALUES(?,?,?)',(rig_id,resource.id,_json(resource.model_dump())))
        store.event(con,'resource_configured',resource.model_dump(),rig_id=rig_id)
    return resource.model_dump()


def remove_resource(store,rig_id,identifier):
    with store.connect(True) as con:
        runtime=con.execute('SELECT enabled FROM rig_runtime WHERE rig_id=?',(rig_id,)).fetchone()
        if not runtime:
            raise KeyError(rig_id)
        if runtime['enabled'] or con.execute("SELECT 1 FROM seats WHERE rig_id=? AND state IN ('BUSY','UNKNOWN')",(rig_id,)).fetchone():
            raise ValueError('Pause and reconcile the team before changing resources')
        con.execute('DELETE FROM resources WHERE rig_id=? AND id=?',(rig_id,identifier))
        store.event(con,'resource_removed',{'id':identifier},rig_id=rig_id)


class Integrations:
    def __init__(self,store):
        self.store=store

    def slack(self):
        with self.store.connect() as con:
            row=con.execute("SELECT spec_json FROM integration_config WHERE id='slack'").fetchone()
        return json.loads(row[0]) if row else {'enabled':False,'channel':None,'token_env':'AI_SCIENTIST_SLACK_TOKEN'}

    def configure_slack(self, *, enabled, channel):
        if type(enabled) is not bool or (enabled and (not isinstance(channel,str) or not channel.startswith('C') or not channel.isalnum())):
            raise ValueError('Slack needs an explicit channel ID')
        config={'enabled':enabled,'channel':channel,'token_env':'AI_SCIENTIST_SLACK_TOKEN'}
        with self.store.connect(True) as con:
            con.execute('INSERT OR REPLACE INTO integration_config VALUES(?,?)',('slack',_json(config)))
            self.store.event(con,'slack_configured',{'enabled':enabled,'channel':channel})
        return config

    def send_slack(self, text, *, authorized=False):
        # Configuration is not permission to send. Each actual external message
        # requires a human action; agents have no credentials with this scope.
        import os
        config=self.slack()
        if not authorized or not config['enabled']:
            raise ValueError('Slack sending requires opt-in and explicit human authorization')
        token=os.environ.get(config['token_env'],'')
        if not token:
            raise ValueError('Slack credential is not configured')
        req=urllib_request.Request('https://slack.com/api/chat.postMessage',
            data=_json({'channel':config['channel'],'text':text}).encode(),
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
        with urllib_request.urlopen(req,timeout=15) as response:
            result=json.loads(response.read(100000))
        if not result.get('ok'):
            raise ValueError('Slack rejected the message')
        self.store.publish('slack_message_sent',{'channel':config['channel'],'timestamp':result.get('ts')})
        return {'channel':config['channel'],'timestamp':result.get('ts')}


def telemetry(control, rig_id):
    team=control.store.snapshot(rig_id)
    totals={}
    for session in team['sessions']:
        provider=session['provider_id']
        entry=totals.setdefault(provider,{'sessions':0,'reported_sessions':0,'input_tokens':None,'output_tokens':None,'cost_usd':None})
        entry['sessions']+=1
        usage=session.get('usage') or {}
        if usage:
            entry['reported_sessions']+=1
        for key in ('input_tokens','output_tokens','cost_usd'):
            value=usage.get(key)
            if isinstance(value,(int,float)) and not isinstance(value,bool):
                entry[key]=(entry[key] or 0)+value
    return {'rig_id':rig_id,'providers':totals,'tasks':{state:sum(t['state']==state for t in team['tasks']) for state in ('PENDING','LEASED','DONE','FAILED','UNKNOWN','CANCELLED')},
        'limits':{'team_parallel':team['spec']['max_parallel'],'pods':team['spec']['pods'],'global_parallel':32,'queue_capacity':256,
                  'windows_cli_acp_terminal_parallel':1 if __import__('os').name=='nt' else None,
                  'resources':[r.model_dump() for r in resource_limits(control.store,rig_id)]},
        'workspaces':[{'seat_id':s['id'],'path':s['worktree'],'checkpoint':s['checkpoint'],'state':s['state']} for s in team['seats']]}
