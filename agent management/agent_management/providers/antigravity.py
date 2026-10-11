"""T3's Antigravity profile, browser interception and ACP launch contract.

Protocol details follow the pinned T3 source recorded in vendor/t3code.
Credentials belong to an instance; IDE/agy credentials are never copied.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from urllib.parse import parse_qs, urlsplit
import uuid

from .installations import atomic_json, node_executable, owned, remove_owned
from .operations import SetupError
from ..acp_sessions import RpcChannel

AUTH_PREFIX='Open the following link to authenticate the ACP server: '
AUTH_MARKER='__T3_ANTIGRAVITY_AUTH_URL__'
AUTH_METHODS=[{'id':'oauth-personal','name':'Google account','type':'agent'},
              {'id':'oauth-business','name':'Gemini Enterprise','type':'agent'},
              {'id':'gemini-api-key','name':'Gemini API key','type':'agent'},
              {'id':'agent-platform','name':'Agent Platform / Vertex AI','type':'agent'}]
REMOVED={'GEMINI_API_KEY','GOOGLE_API_KEY','GOOGLE_APPLICATION_CREDENTIALS','GOOGLE_CLOUD_PROJECT',
         'GOOGLE_CLOUD_LOCATION','GOOGLE_CLOUD_QUOTA_PROJECT','GOOGLE_GENAI_USE_VERTEXAI','GCLOUD_PROJECT',
         'CLOUDSDK_CORE_PROJECT','AGY_ACP_CCPA_PROJECT','AGY_ACP_ENABLE_OAUTH','GEMINI_HOME',
         'AGY_ACP_FORCE_FILE_STORAGE','ANTIGRAVITY_HARNESS_PATH','BROWSER','PYTHONUNBUFFERED','ELECTRON_RUN_AS_NODE'}


def authorization_url(value):
    url=urlsplit(value)
    query=parse_qs(url.query)
    state=query.get('state',[])
    redirect=query.get('redirect_uri',[])
    if (len(value)>16384 or re.search(r'\s',value) or url.scheme!='https' or url.netloc!='accounts.google.com'
        or url.path!='/o/oauth2/v2/auth' or url.fragment or len(state)!=1 or len(redirect)!=1
        or query.get('response_type')!=['code'] or not state[0] or len(state[0])>512
        or not re.fullmatch(r'http://127\.0\.0\.1:[1-9][0-9]{0,4}/',redirect[0])):
        raise SetupError('Antigravity returned an invalid Google sign-in URL.')
    if not 1024<=urlsplit(redirect[0]).port<=65535:
        raise SetupError('Antigravity returned an invalid callback port.')
    return {'authorizationUrl':value,'redirectUri':redirect[0],'state':state[0]}


class AntigravityProfiles:
    def __init__(self, root, temp_root=None):
        self.root=Path(root)
        self.temp_root=Path(temp_root) if temp_root else self.root/'tmp'
        self.root.mkdir(parents=True,exist_ok=True)

    def directory(self, spec):
        key=hashlib.sha256(spec.id.encode()).hexdigest()[:24]
        directory=owned(self.root/'antigravity'/key,self.root)
        directory.mkdir(parents=True,exist_ok=True)
        return directory

    def token(self,spec):
        return self.directory(spec)/'antigravity-acp/acp_token.json'

    def cached(self,spec):
        method=spec.auth_method or 'oauth-personal'
        if method=='agent-platform':return True  # The agent verifies ADC or its API key.
        if method=='gemini-api-key':return bool(spec.api_key)
        return self.token(spec).is_file()

    def environment(self,spec,command,base,*,directory=None):
        profile=Path(directory) if directory else self.directory(spec)
        acp=profile/'antigravity-acp'
        acp.mkdir(parents=True,exist_ok=True)
        method=spec.auth_method or 'oauth-personal'
        gcp={k:v for k,v in [('project',spec.gcp_project),('location',spec.gcp_location)] if v}
        atomic_json(acp/'settings.json',{'auth':{'type':method},**({'gcp':gcp} if gcp else {})})
        # The bundled Python runtime extracts long paths. Keep Windows temp
        # outside the deeply nested account profile, as T3 does.
        temp_root=profile.parent/'tmp' if directory else self.temp_root
        temp_root.mkdir(parents=True,exist_ok=True)
        temp=owned(temp_root/uuid.uuid4().hex[:8],temp_root)
        temp.mkdir()
        node=node_executable().replace('\\','/')
        source='process.stderr.on("error",()=>process.exit(0)).write("'+AUTH_MARKER+'"+JSON.stringify(process.argv[1])+"\\n",()=>process.exit(0))'
        quote=lambda value: "'"+value.replace("'","'\"'\"'")+"'"
        browser=' '.join(map(quote,[node,'-e',source,'--','%s']))
        if (';' if os.name=='nt' else ':') in browser:
            raise SetupError('The Node path cannot be used for Antigravity sign-in.')
        helper=Path(command).parent/('localharness_external.exe' if os.name=='nt' else 'localharness_external')
        if not helper.is_file(): raise SetupError('Antigravity runtime helper is missing.')
        environment={k:v for k,v in base.items() if k.upper() not in REMOVED}
        environment.update(GEMINI_HOME=str(profile),AGY_ACP_FORCE_FILE_STORAGE='1',BROWSER=browser,
            PYTHONUNBUFFERED='1',ANTIGRAVITY_HARNESS_PATH=str(helper),ELECTRON_RUN_AS_NODE='1')
        environment.update({'TEMP':str(temp),'TMP':str(temp)} if os.name=='nt' else {'TMPDIR':str(temp)})
        if method=='gemini-api-key' and spec.api_key: environment['GEMINI_API_KEY']=spec.api_key
        if method=='agent-platform' and spec.api_key: environment['GOOGLE_API_KEY']=spec.api_key
        return environment,temp

    def logout(self,spec):
        token=self.token(spec)
        if token.is_symlink(): raise SetupError('Refusing a linked credential file.')
        token.unlink(missing_ok=True)


class ManagedChannel(RpcChannel):
    def __init__(self,*args,antigravity=False,on_authorization=None,cleanup=None):
        self.antigravity=antigravity
        self.on_authorization=on_authorization
        self.cleanup=cleanup
        self.auth_error=None
        self.stderr_lines=bytearray()
        self.closed=False
        super().__init__(*args)

    def publish_url(self,value):
        if self.antigravity:
            pending=authorization_url(value)
            if self.on_authorization is None:
                self.auth_error=SetupError('Sign in to Antigravity in Config agent before continuing.')
                raise self.auth_error
            self.on_authorization(pending)
        elif self.on_authorization:
            url=urlsplit(value)
            if url.scheme in {'http','https'} and not url.username and not url.password:
                self.on_authorization({'authorizationUrl':value})

    def decode_stdout(self,line):
        text=line.decode('utf-8',errors='replace').strip()
        if self.antigravity and text.startswith(AUTH_PREFIX):
            self.publish_url(text[len(AUTH_PREFIX):])
            return None
        return super().decode_stdout(line)

    def consume_stderr(self,chunk):
        self.stderr_lines.extend(chunk)
        while b'\n' in self.stderr_lines:
            line,_,rest=self.stderr_lines.partition(b'\n')
            self.stderr_lines=bytearray(rest[-32768:])
            text=line.decode('utf-8',errors='replace').strip()
            try:
                if self.antigravity and AUTH_MARKER in text:
                    self.publish_url(json.loads(text.split(AUTH_MARKER,1)[1]))
                elif self.antigravity and text.startswith(AUTH_PREFIX): self.publish_url(text[len(AUTH_PREFIX):])
                elif not self.antigravity and self.on_authorization:
                    match=re.search(r'https?://[^\s<>"\x1b]+',text)
                    if match: self.publish_url(match.group())
            except (ValueError,TypeError) as error:
                self.auth_error=error
                self.failed.set()

    def guard(self):
        if self.auth_error: raise self.auth_error
        super().guard()

    def close(self):
        if self.closed: return self.receipt
        self.closed=True
        try: return super().close()
        finally:
            if self.cleanup: self.cleanup()
