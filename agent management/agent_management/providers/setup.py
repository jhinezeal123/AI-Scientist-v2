"""Application service for provider setup, independent of team/project state."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from threading import RLock
import time
from urllib.parse import parse_qs, urlsplit
import http.client

from .antigravity import AntigravityProfiles, AUTH_METHODS, ManagedChannel
from .catalog import RegistryCatalog
from .installations import Installations, remove_owned
from .operations import SetupError, SetupOperation
from ..acp_sessions import AcpHarness, AcpProtocolError
from ..processes import private_environment


def models_from_session(session):
    from ..harness_models import flatten_choices
    option=next((o for o in session.get('configOptions',[]) if o.get('category')=='model' or o.get('id')=='model'),None)
    if option:
        return [{'slug':row['value'],'name':row.get('name') or row['value'],'isCustom':False,
                 'isDefault':row['value']==option.get('currentValue')} for row in flatten_choices(option.get('options',[]))]
    legacy=session.get('models',{})
    return [{'slug':row['modelId'],'name':row.get('name') or row['modelId'],'isCustom':False,
             'isDefault':row['modelId']==legacy.get('currentModelId')} for row in legacy.get('availableModels',[]) if row.get('modelId')]


class ProviderSetup:
    def __init__(self,catalog,workspace):
        self.catalog,self.workspace=catalog,Path(workspace)
        self.registry=RegistryCatalog(self.workspace/'.workbench/tools/acp-index')
        self.installations=Installations(self.workspace/'.workbench/tools/acp',self.registry)
        self.profiles=AntigravityProfiles(self.workspace/'.workbench/agents/providers/accounts',self.workspace/'.workbench/agy-tmp')
        self.lock=RLock()
        self.installs,self.auth,self.methods,self.snapshots,self.active={},{},{},{},{}

    def spec(self,identifier):
        spec=next((s for s in self.catalog.store.harnesses() if s.id==identifier and not s.archived),None)
        if spec is None: raise SetupError('Provider instance is unavailable.')
        if spec.kind!='acp': raise SetupError('This action is available for ACP providers.')
        return spec

    def launch(self,spec,*,profile=None):
        if spec.registry_agent_id:
            command,args,variables,version=self.installations.resolve(spec)
        else:
            from .installations import native_launch
            command,args=native_launch(AcpHarness(spec).executable(),spec.args)
            variables,version={},None
        environment=private_environment()|variables|spec.environment
        temp=None
        if spec.registry_agent_id=='antigravity-acp':
            environment,temp=self.profiles.environment(spec,command,environment,directory=profile)
        return command,args,environment,version,temp

    def channel(self,spec,timeout=120,*,operation=None,handler=None,profile=None,launch=None,started=lambda _:None):
        command,args,environment,version,temp=launch or self.launch(spec,profile=profile)
        key=spec.registry_agent_id or spec.id
        with self.lock: self.active[key]=self.active.get(key,0)+1
        cleaned=False
        def cleanup():
            nonlocal cleaned
            with self.lock:
                if cleaned:return
                cleaned=True
            try:
                if temp: remove_owned(temp,temp.parent)
            finally:
                with self.lock: self.active[key]=max(0,self.active.get(key,0)-1)
        def publish(pending):
            if not operation: raise SetupError('Sign in to this provider in Config agent.')
            operation.pending=pending
            operation.update(phase='waiting',authorizationUrl=pending['authorizationUrl'],
                interaction={'type':'browser','id':'browser','url':pending['authorizationUrl'],
                    'acceptsCallback':bool(pending.get('redirectUri')),'requiresConsent':False})
        try:
            channel=ManagedChannel([command,*args],self.workspace,timeout,
                operation.cancelled.is_set if operation else lambda:False,
                handler or (lambda _: {'error':{'code':-32601,'message':'Metadata only'}}),
                started,environment,antigravity=spec.registry_agent_id=='antigravity-acp',
                on_authorization=publish if operation else None,cleanup=cleanup)
            if operation: operation.channel=channel
            return channel,version
        except BaseException:
            # ManagedChannel closes a successfully spawned process on constructor failure.
            if not locals().get('channel'): cleanup()
            raise

    def initialize(self,channel,spec):
        adapter=AcpHarness(spec)
        adapter.client_capabilities={'auth':{'terminal':__import__('os').name=='nt'},
            'elicitation':{'url':{}},'fs':{'readTextFile':False,'writeTextFile':False},'terminal':False}
        initialized=adapter.initialize(channel)
        self.methods[spec.id]=initialized.get('authMethods',[])[:32]
        if spec.registry_agent_id=='antigravity-acp': self.methods[spec.id]=AUTH_METHODS
        return initialized

    def authenticate_cached(self,channel,spec):
        if spec.registry_agent_id=='antigravity-acp':
            if not self.profiles.cached(spec): raise SetupError('Sign in with Google to load Antigravity models.')
            channel.rpc('authenticate',{'methodId':spec.auth_method or 'oauth-personal'})

    def metadata(self,spec):
        channel=None
        try:
            if spec.registry_agent_id=='antigravity-acp' and not self.profiles.cached(spec):
                _,_,_,version=self.installations.resolve(spec)
                self.methods[spec.id]=AUTH_METHODS
                value={'models':[],'source':'agent','installed':True,'status':'warning','auth':'unauthenticated',
                    'version':version,'authMethods':AUTH_METHODS,'canLogout':True,
                    'message':'Set the Gemini API key below to load models.' if spec.auth_method=='gemini-api-key' else 'Sign in with Google to load Antigravity models.'}
                with self.lock:self.snapshots[spec.id]=value
                return value
            channel,version=self.channel(spec)
            initialized=self.initialize(channel,spec)
            version=initialized.get('agentInfo',{}).get('version') or version
            self.authenticate_cached(channel,spec)
            session=channel.rpc('session/new',{'cwd':str(self.workspace.resolve()),'mcpServers':[]})
            value={'models':models_from_session(session),'source':'agent','installed':True,'status':'ready',
                   'auth':'authenticated','version':version,'authMethods':self.methods.get(spec.id,[]),
                   'canLogout':bool(initialized.get('agentCapabilities',{}).get('auth',{}).get('logout')),
                   'configOptions':session.get('configOptions',[])}
        except (OSError,ValueError,RuntimeError,TimeoutError) as error:
            installed=channel is not None
            # Protocol diagnostics stay private. Only a known auth requirement is surfaced.
            auth_required=isinstance(error,SetupError) and 'sign in' in str(error).lower()
            auth_required=auth_required or 'authentication required' in str(error).lower()
            value={'models':[],'source':'agent' if installed else 'unavailable','installed':installed,
                   'status':'warning' if auth_required else 'error','auth':'unauthenticated' if auth_required else 'unknown',
                   'version':locals().get('version'),'authMethods':self.methods.get(spec.id,[]),
                   'message':getattr(error,'public_message',None) or ('Sign in to load models.' if auth_required else 'Could not read this ACP agent. Check setup and refresh.')}
        finally:
            if channel: channel.close()
        self.methods.setdefault(spec.id,[])
        value['canAuthenticate']=bool(self.methods[spec.id])
        if spec.registry_agent_id:
            agent=self.registry.agent(spec.registry_agent_id)
            link=agent.get('website') or agent.get('repository') or ''
            if link.startswith('https://'):value['documentationUrl']=link
        with self.lock: self.snapshots[spec.id]=value
        return value

    def install_state(self,spec):
        if not spec.registry_agent_id: return {'instanceId':spec.id,'phase':'unavailable','message':'This provider uses a local executable.'}
        agent=self.registry.agent(spec.registry_agent_id)
        receipt=self.installations.receipt(agent,spec.registry_distribution)
        available={'version':agent['version'],'installedVersion':receipt['version'] if receipt else None,'canRemove':bool(receipt)}
        operation=self.installs.get(spec.registry_agent_id)
        if operation:
            state=operation.public()
            return state|available|{'instanceId':spec.id}
        return {'instanceId':spec.id,'phase':'succeeded' if receipt else 'idle',**available,
                'operationId':None,'message':'Runtime is installed.' if receipt else 'Prepare the runtime to use this agent.'}

    def start_install(self,spec,owner):
        if not spec.registry_agent_id: raise SetupError('Local commands are configured manually.')
        with self.lock:
            previous=self.installs.get(spec.registry_agent_id)
            if previous and previous.thread.is_alive(): return previous.public()|{'instanceId':spec.id}
            if self.active.get(spec.registry_agent_id,0): raise SetupError('Wait for this provider to finish before updating its runtime.')
            operation=SetupOperation(spec.id,owner)
            self.installs[spec.registry_agent_id]=operation
            operation.start(lambda op:self.installations.prepare(spec,op))
        return operation.public()

    def cancel_install(self,spec,owner,identifier):
        operation=self.installs.get(spec.registry_agent_id)
        if not operation or operation.value['operationId']!=identifier or operation.owner!=owner: raise SetupError('This installation is no longer owned by this session.')
        operation.stop()
        return operation.public()

    def remove_installation(self,spec):
        key=spec.registry_agent_id
        with self.lock:
            operation=self.installs.get(key)
            if self.active.get(key,0) or (operation and operation.thread.is_alive()): raise SetupError('This runtime is in use. Finish or cancel setup first.')
            if any(s.registry_agent_id==key and not s.archived and s.enabled for s in self.catalog.store.harnesses()):
                raise SetupError('Disable the instances using this agent before removing its runtime.')
            remove_owned(self.installations.root/key,self.installations.root)
            self.installs.pop(key,None)
        return {'removed':key}

    def auth_state(self,spec,owner):
        operation=self.auth.get(spec.id)
        if operation:
            value=operation.public(owner)
            if spec.registry_agent_id=='antigravity-acp':value['methods']=[m for m in AUTH_METHODS if m['id']==(spec.auth_method or 'oauth-personal')]
            return value
        value={'instanceId':spec.id,'phase':'idle','flowId':None,'authorizationUrl':None,'interaction':None,'expiresAt':None,'message':None}
        if spec.registry_agent_id=='antigravity-acp': value['methods']=[m for m in AUTH_METHODS if m['id']==(spec.auth_method or 'oauth-personal')]
        elif spec.id in self.methods:
            value['methods']=[{'id':m['id'],'name':m.get('name') or m['id'],'type':'credentials' if m.get('type')=='env_var' else m.get('type','agent')} for m in self.methods[spec.id] if m.get('id')]
        return value

    def start_auth(self,spec,owner,method_id=''):
        if not spec.enabled: raise SetupError('Enable this provider before signing in.')
        if spec.registry_agent_id=='antigravity-acp' and method_id and method_id!=(spec.auth_method or 'oauth-personal'):
            raise SetupError('Choose the Antigravity sign-in method in its provider settings first.')
        with self.lock:
            previous=self.auth.get(spec.id)
            if previous and previous.thread.is_alive(): return previous.public(owner)
            operation=SetupOperation(spec.id,owner)
            operation.update(expiresAt=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat())
            self.auth[spec.id]=operation
            operation.start(lambda op:self._authenticate(spec,method_id,op))
        return operation.public(owner)

    def _authenticate(self,spec,method_id,operation):
        channel=None
        try:
            def handler(envelope):
                params=envelope.get('params',{})
                if envelope['method']=='session/elicitation' and params.get('mode')=='url':
                    url=urlsplit(params.get('url',''))
                    if url.scheme not in {'http','https'} or url.username or url.password: return {'result':{'action':'decline'}}
                    ident=str(params.get('elicitationId','browser'))[:128]
                    operation.update(phase='waiting',interaction={'type':'browser','id':ident,'url':params['url'],'requiresConsent':True})
                    response=operation.response(ident)
                    return {'result':{'action':response.get('action','decline')}}
                return {'error':{'code':-32601,'message':'Provider sign-in only'}}
            channel,_=self.channel(spec,300,operation=operation,handler=handler)
            self.initialize(channel,spec)
            methods=self.methods.get(spec.id,[])
            method_id=method_id or spec.auth_method or next((m['id'] for m in methods if m.get('type','agent')!='env_var'),methods[0]['id'] if methods else '')
            method=next((m for m in methods if m['id']==method_id),None)
            if not method: raise SetupError('This agent does not advertise an in-app sign-in method. Open its documentation for setup.')
            operation.update(methods=[{'id':m['id'],'name':m.get('name') or m['id'],'type':m.get('type','agent')} for m in methods])
            if method.get('type')=='terminal':
                channel.close();channel=None
                from .terminal_auth import terminal_login
                command,args,environment,_,temp=self.launch(spec)
                try: terminal_login([command,*args,*method.get('args',[])],self.workspace,environment|method.get('env',{}),operation)
                finally:
                    if temp: remove_owned(temp,temp.parent)
                channel,_=self.channel(spec,90,operation=operation,handler=handler)
                self.initialize(channel,spec)
            elif method.get('type')=='env_var':
                fields=[{'name':v['name'],'label':v.get('description') or v['name'],'secret':True} for v in method.get('vars',[]) if v.get('name')][:16]
                if not fields: raise SetupError('Set this agent’s API key in its environment settings.')
                operation.update(phase='waiting',interaction={'type':'credentials','id':'credentials','fields':fields})
                values=operation.response('credentials').get('values',{})
                channel.close();channel=None
                from ..models import HarnessSpec
                from ..harness_settings import HarnessSettings
                environment=spec.environment|{f['name']:values.get(f['name'],'') for f in fields}
                sensitive=set(spec.environment_sensitive or spec.environment)|{f['name'] for f in fields}
                spec=HarnessSpec.model_validate(spec.model_dump()|{'environment':environment,'environment_sensitive':sorted(sensitive)})
                HarnessSettings(self.catalog).put(spec)
                channel,_=self.channel(spec,90,operation=operation,handler=handler)
                self.initialize(channel,spec)
            else:
                channel.rpc('authenticate',{'methodId':method_id})
            operation.update(phase='verifying',interaction=None,authorizationUrl=None)
            session=channel.rpc('session/new',{'cwd':str(self.workspace.resolve()),'mcpServers':[]})
            self.snapshots[spec.id]={'models':models_from_session(session),'source':'agent','installed':True,'status':'ready','auth':'authenticated'}
            operation.update(phase='succeeded',message='Signed in. Models are available.',interaction=None,authorizationUrl=None)
        except AcpProtocolError as error:
            if 'SUBSCRIPTION_REQUIRED' in str(error.diagnostic): raise SetupError('Google requires an eligible Antigravity subscription for this account.') from None
            raise
        finally:
            if channel: channel.close()

    def respond(self,spec,owner,body):
        operation=self.flow(spec,owner,body['flowId'])
        interaction=operation.value.get('interaction')
        if not interaction or interaction['id']!=body['interactionId']: raise SetupError('This sign-in step is no longer pending.')
        response=body['response']
        if response['type']!=interaction['type']: raise SetupError('This response does not match the current sign-in step.')
        if interaction['type']=='terminal':
            if getattr(operation,'terminal',None) is None: raise SetupError('The sign-in terminal has closed.')
            if response.get('size'): operation.terminal.setwinsize(response['size']['rows'],response['size']['cols'])
            if response.get('data'): operation.terminal.write(response['data'])
        else:
            with operation.lock: operation.responses[interaction['id']]=response
            operation.changed.set()
        return operation.public(owner)

    def flow(self,spec,owner,identifier):
        operation=self.auth.get(spec.id)
        if not operation or operation.owner!=owner or operation.value['flowId']!=identifier or not operation.thread.is_alive():
            raise SetupError('This sign-in flow has expired. Start sign-in again.')
        return operation

    def complete_auth(self,spec,owner,body):
        operation=self.flow(spec,owner,body['flowId'])
        pending=getattr(operation,'pending',None)
        callback=urlsplit(body['callbackUrl'])
        expected=urlsplit(pending['redirectUri']) if pending and pending.get('redirectUri') else None
        query=parse_qs(callback.query)
        if (expected is None or callback.scheme!='http' or callback.netloc!=expected.netloc or callback.path!=expected.path
            or callback.fragment or callback.username or callback.password or query.get('state')!=[pending['state']]
            or not ((len(query.get('code',[]))==1 and not query.get('error')) or (len(query.get('error',[]))==1 and not query.get('code')))):
            raise SetupError('This callback URL does not belong to the current Google sign-in.')
        with operation.lock:
            if getattr(operation,'callback_sent',False): raise SetupError('This sign-in callback has already been delivered.')
            operation.callback_sent=True
        connection=http.client.HTTPConnection('127.0.0.1',expected.port,timeout=10)
        try:
            connection.request('GET',callback.path+'?'+callback.query)
            response=connection.getresponse();response.read(32768)
            if not 200<=response.status<300: raise SetupError('Could not deliver the sign-in callback.')
        except (OSError,SetupError):
            with operation.lock: operation.callback_sent=False
            raise SetupError('Could not deliver the sign-in callback. Check the URL and retry.') from None
        finally: connection.close()
        return operation.public(owner)

    def cancel_auth(self,spec,owner,identifier):
        operation=self.flow(spec,owner,identifier)
        operation.stop()
        return operation.public(owner)

    def logout(self,spec,owner):
        with self.lock:
            if self.active.get(spec.registry_agent_id or spec.id,0): raise SetupError('Finish or cancel active provider sessions before signing out.')
        if spec.registry_agent_id=='antigravity-acp':
            self.profiles.logout(spec)
            if spec.api_key:
                from ..harness_settings import HarnessSettings
                HarnessSettings(self.catalog).put(spec.model_copy(update={'api_key':''}))
        else:
            channel,_=self.channel(spec,60)
            try:
                initialized=self.initialize(channel,spec)
                if not initialized.get('agentCapabilities',{}).get('auth',{}).get('logout'): raise SetupError('This agent does not advertise sign-out. Use its own account settings.')
                channel.rpc('logout',{})
            finally: channel.close()
        self.auth.pop(spec.id,None);self.snapshots.pop(spec.id,None)
        return self.auth_state(spec,owner)

    def close(self):
        for operation in [*self.installs.values(),*self.auth.values()]: operation.stop()
        for operation in [*self.installs.values(),*self.auth.values()]:
            if operation.thread: operation.thread.join(timeout=2)
