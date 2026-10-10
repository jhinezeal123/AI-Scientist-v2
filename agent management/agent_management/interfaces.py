"""CLI, terminal UI and MCP clients. The existing HTTP server remains sole owner."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import sys
from urllib import request, error, parse


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Control API redirects are not allowed')


class Client:
    def __init__(self,url='http://127.0.0.1:8000',token=None,*,agent=False):
        parsed=parse.urlsplit(url)
        if parsed.username or parsed.password or parsed.path not in {'','/'} or parsed.query or parsed.fragment:
            raise ValueError('Control URL must be an origin')
        try:
            local=ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            local=parsed.hostname=='localhost'
        if parsed.scheme!='https' and not (parsed.scheme=='http' and local):
            raise ValueError('Remote API credentials require HTTPS')
        self.url=url.rstrip('/')+'/api/agent-management'
        self.token=token or os.environ.get('AI_SCIENTIST_AGENT_DEVICE_TOKEN','')
        if not self.token and not agent:
            self.token=os.environ.get('AI_SCIENTIST_AGENT_CONTROL_TOKEN','')
        if not self.token:
            raise ValueError('Configure a scoped device credential (MCP never accepts the bootstrap environment token)')

    def call(self,path,method='GET',body=None):
        if not path.startswith('/') or path.startswith('//') or '\\' in path or '..' in parse.unquote(path).split('/'):
            raise ValueError('Invalid control API path')
        req=request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,method=method,
            headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        try:
            with request.build_opener(NoRedirect()).open(req,timeout=140) as response:
                data=response.read(10000001)
                if len(data)>10000000:
                    raise ValueError('Control response exceeds 10MB')
                return json.loads(data)
        except error.HTTPError as exc:
            detail=json.loads(exc.read(20000)).get('detail','Control API rejected request')
            raise ValueError(str(detail)) from None


def tui(client,*,once=False):
    while True:
        teams=client.call('/teams')
        print('TEAM                         STATE       SEATS')
        for team in teams:
            print(f"{team['id'][:28]:28} {'RUNNING' if team['enabled'] else 'PAUSED':10} {len(team['spec']['seats'])}")
        if once:
            return
        choice=input('\nTeam ID (Enter refresh, q quit): ').strip()
        if choice=='q':
            return
        if not choice:
            continue
        if choice not in {t['id'] for t in teams}:
            print('Unknown team')
            continue
        team=client.call('/teams/'+choice)
        print(json.dumps(team,ensure_ascii=False,indent=2))
        command=input('[s]tart, [p]ause, [m]essage, [t]ask, Enter back: ').strip()
        try:
            if command in {'s','p'}:
                print(client.call('/teams/'+choice+('/start' if command=='s' else '/pause?interrupt=true'),'POST'))
            elif command=='m':
                print(client.call('/teams/'+choice+'/messages','POST',{'sender':input('Sender seat: '),'recipient':input('Recipient (* broadcast): '),'body':input('Message: ')}))
            elif command=='t':
                import uuid
                print(client.call('/teams/'+choice+'/tasks','POST',{'seat':input('Seat: '),'request_id':uuid.uuid4().hex,'task':{'instruction':input('Task: ')}}))
        except ValueError as exc:
            print(str(exc))


class Mcp:
    def __init__(self,client):
        self.client=client
        self.initialized=False
        self.negotiated=False

    def handle(self,message):
        method=message.get('method')
        params=message.get('params',{})
        if method=='initialize':
            if self.negotiated:
                raise ValueError('Already initialized')
            self.negotiated=True
            return {'protocolVersion':'2025-11-25','capabilities':{'tools':{},'resources':{}},
                'serverInfo':{'name':'ai-scientist-teams','version':'1.0.0'}}
        if method=='notifications/initialized':
            self.initialized=self.negotiated
            return None
        if method=='ping':
            return {}
        if not self.initialized:
            raise ValueError('Initialize MCP before calling tools')
        if method=='tools/list':
            return {'tools':[{'name':'team_control','description':'Read scoped teams, enqueue coding work and send messages through the existing control plane. Research authorization and human permissions are enforced by the API.',
                'inputSchema':{'type':'object','additionalProperties':False,'required':['path'],
                    'properties':{'path':{'type':'string'},'method':{'type':'string','enum':['GET','POST','PUT','DELETE']},'body':{'type':'object'}}}}]}
        if method=='tools/call':
            if params.get('name')!='team_control':
                raise ValueError('Unknown MCP tool')
            args=params.get('arguments',{})
            if set(args)-{'path','method','body'} or 'path' not in args:
                raise ValueError('Invalid tool arguments')
            try:
                result=self.client.call(args['path'],args.get('method','GET'),args.get('body'))
                return {'content':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}],'structuredContent':{'result':result},'isError':False}
            except ValueError as exc:
                return {'content':[{'type':'text','text':str(exc)}],'isError':True}
        if method=='resources/list':
            return {'resources':[{'uri':'teams://'+r['id'],'name':r['spec']['name'],'mimeType':'application/json'} for r in self.client.call('/teams')]}
        if method=='resources/read':
            uri=params.get('uri','')
            identifier=uri.removeprefix('teams://')
            from .spec import _id
            _id(identifier,'team ID')
            if not uri.startswith('teams://'):
                raise ValueError('Unknown resource URI')
            value=self.client.call('/teams/'+identifier)
            return {'contents':[{'uri':uri,'mimeType':'application/json','text':json.dumps(value,ensure_ascii=False)}]}
        raise ValueError('Unsupported MCP method')

    def stdio(self,input_stream=None,output_stream=None):
        source=input_stream or sys.stdin
        target=output_stream or sys.stdout
        for line in source:
            if len(line.encode())>1000000:
                break
            message=None
            try:
                message=json.loads(line)
                if not isinstance(message,dict) or message.get('jsonrpc')!='2.0':
                    raise ValueError('Invalid JSON-RPC envelope')
                result=self.handle(message)
                response={'jsonrpc':'2.0','id':message.get('id'),'result':result}
            except (ValueError,KeyError,TypeError) as exc:
                response={'jsonrpc':'2.0','id':message.get('id') if isinstance(message,dict) else None,'error':{'code':-32602,'message':str(exc)}}
            if not isinstance(message,dict) or 'id' in message:
                print(json.dumps(response,ensure_ascii=False),file=target,flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description='AI Scientist team controls')
    parser.add_argument('--url',default='http://127.0.0.1:8000')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('teams')
    terminal_ui=sub.add_parser('tui');terminal_ui.add_argument('--once',action='store_true')
    sub.add_parser('mcp')
    call=sub.add_parser('call');call.add_argument('method',choices=['GET','POST','PUT','DELETE']);call.add_argument('path');call.add_argument('--body-file',type=Path)
    args=parser.parse_args(argv)
    client=Client(args.url,agent=args.command=='mcp')
    if args.command=='mcp':
        Mcp(client).stdio()
    elif args.command=='tui':
        tui(client,once=args.once)
    else:
        value=client.call('/teams') if args.command=='teams' else client.call(args.path,args.method,json.loads(args.body_file.read_text(encoding='utf-8')) if args.body_file else None)
        print(json.dumps(value,ensure_ascii=False,indent=2))
