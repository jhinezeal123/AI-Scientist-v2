"""Opt-in Slack configuration and explicit message delivery."""
import json
from urllib import request as urllib_request

from .store import _json


class SlackIntegration:
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

