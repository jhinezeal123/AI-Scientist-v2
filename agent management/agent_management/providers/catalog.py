"""The official ACP Registry used by T3, with a bounded offline cache."""
import json
import platform
import re
import sys
import time
from pathlib import Path
from threading import RLock
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

REGISTRY_URL = 'https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json'
ID = re.compile(r'^[a-z0-9][a-z0-9._-]{0,127}$')
VERSION = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$')


def https_url(value):
    parts = urlsplit(value)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or len(value)>2048:
        raise ValueError('Registry download must use HTTPS')
    return value


def platform_target():
    system = {'win32':'windows','darwin':'darwin'}.get(sys.platform,'linux')
    arch = 'aarch64' if platform.machine().lower() in {'arm64','aarch64'} else 'x86_64'
    return system+'-'+arch


class RegistryCatalog:
    def __init__(self, root):
        self.root, self._lock = Path(root), RLock()
        self._value, self._at, self.stale = None, 0, False

    def index(self, refresh=False):
        with self._lock:
            if self._value is not None and not refresh and time.monotonic()-self._at < 3600:
                return self._value
            try:
                with urlopen(Request(REGISTRY_URL,headers={'User-Agent':'AI-Scientist-Workbench'}),timeout=25) as response:
                    if response.status != 200:
                        raise ValueError('Registry request failed')
                    data = response.read(1_048_577)
                    if len(data)>1_048_576:
                        raise ValueError('Registry exceeds its limit')
                value = self.validate(json.loads(data))
                self.root.mkdir(parents=True,exist_ok=True)
                temporary=self.root/'registry.tmp'
                temporary.write_bytes(data)
                temporary.replace(self.root/'registry.json')
                self.stale=False
            except (OSError,ValueError):
                cached=self.root/'registry.json'
                bundled=Path(__file__).parents[1]/'vendor/t3code/acp-registry.json'
                value=self._value
                for candidate in (cached,bundled):
                    if value is not None: break
                    try:
                        if candidate.stat().st_size<=1_048_576:
                            value=self.validate(json.loads(candidate.read_text(encoding='utf-8')))
                    except (OSError,ValueError):
                        pass
                if value is None:
                    raise ValueError('Cannot load ACP Registry. Check the connection and retry.') from None
                self.stale=True
            self._value, self._at = value,time.monotonic()
            return value

    @staticmethod
    def validate(value):
        if not isinstance(value,dict) or not isinstance(value.get('agents'),list) or len(value['agents'])>512:
            raise ValueError('Invalid ACP Registry')
        agents=[]
        for row in value['agents']:
            if not isinstance(row,dict) or not ID.fullmatch(row.get('id','')) or not VERSION.fullmatch(row.get('version','')):
                continue
            if not isinstance(row.get('distribution'),dict) or not isinstance(row.get('name'),str):
                continue
            agents.append(row)
        return {'version':value.get('version','1'), 'agents':agents}

    def agent(self, identifier):
        if not ID.fullmatch(identifier): raise ValueError('Invalid registry agent')
        agent=next((a for a in self.index()['agents'] if a['id']==identifier),None)
        if agent is None: raise ValueError('Agent is not in the ACP Registry')
        return agent

    def distribution(self, agent, preference='auto'):
        available=agent['distribution']
        for kind in (('binary','npx','uvx') if preference=='auto' else (preference,)):
            item=available.get('binary',{}).get(platform_target()) if kind=='binary' else available.get(kind)
            if item: return kind,item
        return None,None

    def search(self, query='', refresh=False):
        value=self.index(refresh)
        terms=query.casefold().split()
        rows=[]
        for agent in value['agents']:
            text=' '.join(str(agent.get(k,'')) for k in ('id','name','description')).casefold()
            if not all(term in text for term in terms): continue
            kind,_=self.distribution(agent)
            rows.append({k:agent[k] for k in ('id','name','version','description','website','repository','icon') if k in agent} |
                        {'distribution':kind,'supported':bool(kind)})
        return {'agents':rows,'version':value['version'],'platform':platform_target(),'stale':self.stale}
