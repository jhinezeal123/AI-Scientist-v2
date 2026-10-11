"""Managed ACP distributions, following T3's binary → npm → uv selection.

Each exact registry release has an install receipt. Preparation is explicit;
normal model probes and workflow turns never download or update an agent.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile
import time
from urllib.request import Request, urlopen
import uuid
import zipfile

from .catalog import https_url
from .operations import SetupError
from ..processes import private_environment, run_process

PACKAGE = re.compile(r'^(?:@[^/@\s]+/[^@\s]+|[a-z0-9][a-z0-9._-]*)@v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$')
UV_PACKAGE = re.compile(r'^[a-z0-9][a-z0-9._-]*(?:@|==)v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$',re.I)


def owned(path, root):
    if Path(root).is_symlink() or getattr(Path(root),'is_junction',lambda:False)():
        raise SetupError('Linked provider storage cannot be used.')
    path,root=Path(path),Path(root).resolve()
    if not path.resolve().is_relative_to(root) or path.resolve()==root:
        raise SetupError('Runtime path is outside the provider storage.')
    for candidate in (path,*path.parents):
        if candidate==root: break
        if candidate.is_symlink() or getattr(candidate,'is_junction',lambda:False)():
            raise SetupError('Linked provider storage cannot be used.')
    return path


def remove_owned(path, root):
    path=owned(path,root)
    if path.exists(): shutil.rmtree(path)


def atomic_json(path, value):
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    temporary.replace(path)


def node_executable():
    value=shutil.which('node.exe') or shutil.which('node')
    if not value: raise SetupError('Install Node.js to prepare this ACP agent.')
    return value


def native_launch(command, args):
    command=Path(command)
    if command.suffix.lower() in {'.cmd','.bat'}:
        # Translate the downloaded Node launcher to literal argv, never cmd /c.
        source=command.read_text(encoding='utf-8',errors='replace')[:32768]
        references=re.findall(r'"([^"\r\n]+\.(?:mjs|cjs|js))"',source,re.I)
        for reference in references:
            reference=reference.replace('%~dp0',str(command.parent)+os.sep).replace('%dp0%',str(command.parent)+os.sep)
            script=Path(reference.replace('\\',os.sep))
            if script.is_file():
                bundled=command.parent/'node.exe'
                return str(bundled if bundled.is_file() else node_executable()),[str(script),*args]
        raise SetupError('This Windows launcher could not be resolved. Use a native executable override.')
    if not command.is_file(): raise SetupError('The installed ACP executable is missing.')
    with command.open('rb') as header: is_node=header.read(100).startswith(b'#!/usr/bin/env node')
    if command.suffix.lower() in {'.js','.mjs','.cjs'} or is_node:
        return node_executable(),[str(command),*args]
    if not command.is_file(): raise SetupError('The installed ACP executable is missing.')
    if os.name!='nt': command.chmod(command.stat().st_mode|stat.S_IXUSR)
    return str(command),list(args)


class Installations:
    def __init__(self, root, catalog):
        self.root,self.catalog=Path(root),catalog
        self.root.mkdir(parents=True,exist_ok=True)

    def directory(self, agent, kind):
        return owned(self.root/agent['id']/agent['version']/kind,self.root)

    def receipt(self, agent, preference='auto', *, exact=False):
        kind,_=self.catalog.distribution(agent,preference)
        if not kind: return None
        directory=self.directory(agent,kind)
        candidates=[directory]
        if not exact:
            base=owned(self.root/agent['id'],self.root)
            candidates += sorted((p.parent for p in base.glob('*/'+('*' if preference=='auto' else preference)+'/install.json')),key=lambda p:p.stat().st_mtime,reverse=True)
        for directory in dict.fromkeys(candidates):
            record=self._receipt(agent,directory)
            if record: return record
        return None

    def _receipt(self,agent,directory):
        try:
            directory=owned(directory,self.root)
            record=json.loads((directory/'install.json').read_text(encoding='utf-8'))
            if record['agentId']!=agent['id'] or record['version']!=directory.parent.name: return None
            entry=owned(directory/record['entrypoint'],directory)
            if not entry.is_file(): return None
            if agent['id']=='antigravity-acp' and not (entry.parent/('localharness_external.exe' if os.name=='nt' else 'localharness_external')).is_file(): return None
            return record|{'directory':str(directory),'entrypoint':str(entry)}
        except (OSError,ValueError,KeyError,TypeError): return None

    def resolve(self, spec):
        agent=self.catalog.agent(spec.registry_agent_id)
        kind,distribution=self.catalog.distribution(agent,spec.registry_distribution)
        if not kind: raise SetupError('This ACP agent has no distribution for this operating system.')
        args=distribution.get('args',[])
        environment=distribution.get('env',{})
        if spec.executable:
            candidate=shutil.which(spec.executable) or spec.executable
            command,args=native_launch(candidate,[*args,*spec.args])
            return command,args,environment,agent['version']
        record=self.receipt(agent,spec.registry_distribution)
        if record is None: raise SetupError('Prepare this ACP agent in Config agent before using it.')
        if record['version']!=agent['version'] or record['distribution']!=kind:
            args=record.get('args',[])
            environment=record.get('env',{})
        command,args=native_launch(record['entrypoint'],[*args,*spec.args])
        return command,args,environment,record['version']

    def prepare(self, spec, operation):
        agent=self.catalog.agent(spec.registry_agent_id)
        kind,distribution=self.catalog.distribution(agent,spec.registry_distribution)
        if not kind: raise SetupError('This ACP agent has no distribution for this operating system.')
        if self.receipt(agent,spec.registry_distribution,exact=True):
            operation.update(phase='succeeded',message='Runtime is installed.',version=agent['version'])
            return
        destination=self.directory(agent,kind)
        staging=destination if kind=='uvx' else owned(self.root/('.stage-'+uuid.uuid4().hex),self.root)
        if kind=='uvx' and staging.exists(): remove_owned(staging,self.root)
        staging.mkdir(parents=True)
        success=False
        try:
            operation.guard()
            if kind=='binary': entry=self.binary(distribution,staging,operation)
            elif kind=='npx': entry=self.npm(distribution,staging,operation)
            else: entry=self.uv(distribution,staging,operation)
            operation.guard()
            if not entry.is_file(): raise SetupError('The archive does not contain the declared ACP executable.')
            if agent['id']=='antigravity-acp' and not (entry.parent/('localharness_external.exe' if os.name=='nt' else 'localharness_external')).is_file():
                raise SetupError('The Antigravity runtime helper is missing.')
            operation.update(phase='verifying',message='Verifying installation…')
            relative=entry.relative_to(staging).as_posix()
            atomic_json(staging/'install.json',{'agentId':agent['id'],'version':agent['version'],
                        'distribution':kind,'entrypoint':relative,'preparedAt':time.time(),
                        'args':distribution.get('args',[]),'env':distribution.get('env',{})})
            destination.parent.mkdir(parents=True,exist_ok=True)
            if staging!=destination:
                if destination.exists(): remove_owned(destination,self.root)
                staging.replace(destination)
            success=True
            operation.update(phase='succeeded',message='Runtime is installed.',version=agent['version'],progress=None)
        finally:
            if not success and staging.exists(): remove_owned(staging,self.root)

    def binary(self, distribution, staging, operation):
        address=https_url(distribution['archive'])
        archive=staging/'download.archive'
        operation.update(phase='downloading',message='Downloading runtime…',progress=0)
        digest=hashlib.sha256()
        with urlopen(Request(address,headers={'User-Agent':'AI-Scientist-Workbench'}),timeout=30) as response, archive.open('wb') as stream:
            length=int(response.headers.get('Content-Length','0'))
            if length>1_073_741_824: raise SetupError('Runtime archive exceeds the download limit.')
            downloaded=0
            while chunk:=response.read(262144):
                operation.guard()
                downloaded+=len(chunk)
                if downloaded>1_073_741_824: raise SetupError('Runtime archive exceeds the download limit.')
                digest.update(chunk)
                stream.write(chunk)
                operation.update(progress=round(downloaded/length*100) if length else None,downloadedBytes=downloaded,totalBytes=length or None)
        if distribution.get('sha256') and digest.hexdigest().lower()!=distribution['sha256'].lower():
            raise SetupError('Runtime download checksum does not match the registry.')
        operation.update(phase='extracting',message='Extracting runtime…',progress=None)
        payload=staging/'runtime'
        payload.mkdir()
        def destination(name):
            name=name.replace('\\','/')
            relative=PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or any(':' in part for part in relative.parts):
                raise SetupError('Runtime archive contains an unsafe path.')
            return payload.joinpath(*relative.parts)
        expanded=0
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as package:
                if len(package.infolist())>50000: raise SetupError('Too many files in runtime archive.')
                for member in package.infolist():
                    operation.guard()
                    if stat.S_ISLNK(member.external_attr>>16): raise SetupError('Runtime archive contains an unsupported link.')
                    expanded+=member.file_size
                    if expanded>4_294_967_296: raise SetupError('Runtime archive exceeds the extraction limit.')
                    target=destination(member.filename)
                    if member.is_dir(): target.mkdir(parents=True,exist_ok=True); continue
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with package.open(member) as source,target.open('wb') as output: shutil.copyfileobj(source,output,262144)
        else:
            with tarfile.open(archive) as package:
                for index,member in enumerate(package):
                    operation.guard()
                    if index>50000 or not (member.isfile() or member.isdir()): raise SetupError('Runtime archive contains an unsupported entry.')
                    expanded+=member.size
                    if expanded>4_294_967_296: raise SetupError('Runtime archive exceeds the extraction limit.')
                    target=destination(member.name)
                    if member.isdir(): target.mkdir(parents=True,exist_ok=True); continue
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with package.extractfile(member) as source,target.open('wb') as output: shutil.copyfileobj(source,output,262144)
                    if os.name!='nt': target.chmod(member.mode&0o777)
        archive.unlink()
        relative=distribution['cmd'].removeprefix('./').replace('\\','/')
        entry=owned(payload/relative,payload)
        if os.name=='nt' and not entry.exists() and entry.with_suffix('.exe').exists(): entry=entry.with_suffix('.exe')
        return entry

    def npm(self, distribution, staging, operation):
        package=distribution['package']
        if not PACKAGE.fullmatch(package): raise SetupError('Registry npm package must use an exact version.')
        node=Path(node_executable())
        candidates=[node.parent/'node_modules/npm/bin/npm-cli.js',node.parent.parent/'lib/node_modules/npm/bin/npm-cli.js']
        npm=next((p for p in candidates if p.is_file()),None)
        if npm is None: raise SetupError('Install npm to prepare this ACP agent.')
        operation.update(phase='downloading',message='Preparing npm package…')
        package_root=staging/'runtime'
        package_root.mkdir()
        run_process([str(node),str(npm),'install','--prefix',str(package_root),'--no-audit','--no-fund','--no-save',package],
            staging,b'',timeout=1200,cancelled=operation.cancelled.is_set,env=private_environment(),emit=lambda _:None,limit=2_000_000)
        package_name=package.rsplit('@',1)[0]
        installed=package_root/'node_modules'/package_name
        manifest=json.loads((installed/'package.json').read_text(encoding='utf-8'))
        binary=manifest.get('bin')
        if isinstance(binary,dict): binary=binary.get(package_name.split('/')[-1]) or next(iter(binary.values()),None)
        if not isinstance(binary,str): raise SetupError('The npm package has no ACP executable.')
        return owned(installed/binary,installed)

    def uv(self, distribution, staging, operation):
        package=distribution['package']
        if not UV_PACKAGE.fullmatch(package): raise SetupError('Registry Python package must use an exact version.')
        executable=shutil.which('uv.exe') or shutil.which('uv')
        if not executable: raise SetupError('Install uv to prepare this ACP agent.')
        operation.update(phase='downloading',message='Preparing Python package…')
        package_root=staging/'runtime'
        environment=private_environment()|{'UV_TOOL_DIR':str(package_root/'tools'),'UV_TOOL_BIN_DIR':str(package_root/'bin')}
        # The caller installs uv directly into its final version directory.
        package_root.mkdir()
        run_process([executable,'tool','install',package.replace('@','=='),'--force'],staging,b'',timeout=1200,
                    cancelled=operation.cancelled.is_set,env=environment,emit=lambda _:None,limit=2_000_000)
        binaries=list((package_root/'bin').glob('*.exe' if os.name=='nt' else '*'))
        if not binaries: raise SetupError('The Python package has no ACP executable.')
        return binaries[0]
