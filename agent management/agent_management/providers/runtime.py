"""Managed distributions use the existing supervised ACP session contract."""
import hashlib
import os
from pathlib import Path
import shutil

from .antigravity import ManagedChannel
from .installations import owned, remove_owned
from .operations import SetupError
from ..acp_sessions import AcpHarness
from ..processes import private_environment


class ManagedAcpHarness(AcpHarness):
    def __init__(self,spec,setup,**kwargs):
        command,args,variables,_=setup.installations.resolve(spec)
        self.provider_spec,self.setup=spec,setup
        super().__init__(spec.model_copy(update={'executable':command,'args':args,
                         'environment':variables|spec.environment}),**kwargs)

    def initialize(self,channel):
        result=super().initialize(channel)
        self.setup.authenticate_cached(channel,self.provider_spec)
        return result

    def open_channel(self,*args):
        return ManagedChannel(*args,antigravity=self.provider_spec.registry_agent_id=='antigravity-acp')

    def send(self,handle,message,**kwargs):
        from ..project_storage import data_root
        root=data_root(self.setup.workspace,handle.workspace)/'runtimes'
        root.mkdir(parents=True,exist_ok=True)
        key=hashlib.sha256((self.provider_spec.id+'\0'+str(handle.workspace.resolve())).encode()).hexdigest()[:24]
        home=owned(root/('acp-'+key),root)
        if home.exists() and os.name=='nt' and self.sandbox:
            from ..windows_isolation import refresh_scope
            refresh_scope(self.setup.workspace,[home])
        home.mkdir(exist_ok=True)
        profile=home/'profile'
        profile.mkdir(exist_ok=True)
        source_token=None
        if self.provider_spec.registry_agent_id=='antigravity-acp':
            source_token=self.setup.profiles.token(self.provider_spec)
            if source_token.is_file():
                target=profile/'antigravity-acp/acp_token.json'
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source_token,target)
        command,args,environment,_,temp=self.setup.launch(self.provider_spec,profile=profile)
        # Native ACP wrappers get only their own saved CLI authentication in the
        # writable runtime scope. Their credential stores remain outside tools.
        native_auth={'codex-acp':('CODEX_HOME',Path.home()/'.codex',['auth.json']),
                     'claude-acp':('CLAUDE_CONFIG_DIR',Path.home()/'.claude',['.credentials.json'])}
        if self.provider_spec.registry_agent_id in native_auth:
            variable,source,names=native_auth[self.provider_spec.registry_agent_id]
            source=Path(self.provider_spec.environment.get(variable) or source).expanduser()
            for name in names:
                if (source/name).is_file() and not (source/name).is_symlink(): shutil.copyfile(source/name,profile/name)
            environment[variable]=str(profile)
        environment['WORKBENCH_PROVIDER_HOME']=str(home)
        temporary=home/'tmp'
        temporary.mkdir(exist_ok=True)
        if not temp: environment.update(TEMP=str(temporary),TMP=str(temporary),TMPDIR=str(temporary))
        previous=self.spec
        self.spec=self.spec.model_copy(update={'environment':environment})
        key=self.provider_spec.registry_agent_id
        with self.setup.lock: self.setup.active[key]=self.setup.active.get(key,0)+1
        try: return super().send(handle,message,**kwargs)
        finally:
            self.spec=previous
            if temp and temp.exists(): remove_owned(temp,temp.parent)
            # Only this instance's ACP token is synced after its process stops.
            updated=profile/'antigravity-acp/acp_token.json'
            if source_token and updated.is_file() and not updated.is_symlink() and updated.stat().st_size<=65536:
                shutil.copyfile(updated,source_token)
            with self.setup.lock: self.setup.active[key]=max(0,self.setup.active.get(key,0)-1)
