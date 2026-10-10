"""Serialize sandbox ACL changes on Windows and refresh only the owned scope.

The installed Codex sandbox uses persistent CodexSandboxUsers deny ACLs. A
later seat cannot read a worktree denied by an earlier seat until that deny is
removed. Serialize these CLI/ACP/terminal turns so refreshing the current scope
cannot widen access for another supervised sandbox. Native tool-free turns
continue to run concurrently; Kaggle admission remains independent.
"""
from contextlib import contextmanager
import base64
import json
import os
from pathlib import Path
import subprocess
import shutil
from threading import RLock, local
import time

_lock=RLock()
_state=local()


@contextmanager
def lease(timeout, cancelled=lambda:False):
    if os.name!='nt':
        yield
        return
    deadline=time.monotonic()+timeout
    while not _lock.acquire(timeout=.1):
        if cancelled():
            raise InterruptedError('Sandbox wait cancelled before execution')
        if time.monotonic()>=deadline:
            raise ValueError('Windows sandbox resource is busy; no process was started')
    previous=getattr(_state,'held',False)
    _state.held=True
    try:
        if cancelled():
            raise InterruptedError('Sandbox wait cancelled before execution')
        yield
    finally:
        _state.held=previous
        _lock.release()


def scope_acl(repository, paths, *, deny=False, legacy=False):
    if os.name!='nt':
        return
    if not getattr(_state,'held',False):
        raise ValueError('Sandbox ACL refresh requires exclusive runtime ownership')
    roots=[repository/'.workbench/agents/worktrees',repository/'.workbench/agents/runtimes']
    if legacy:
        roots.append(repository/'.workbench/projects')
    checked=[]
    for path in paths:
        path=Path(path)
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)() or not any(path.resolve().is_relative_to(r.resolve()) for r in roots):
            raise ValueError('Sandbox ACL scope must be an owned worktree or runtime directory')
        checked.append(str(path.resolve(strict=True)))
    payload=base64.b64encode(json.dumps(checked).encode()).decode()
    script="""$ErrorActionPreference='Stop';
$targetPaths=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('PAYLOAD'))|ConvertFrom-Json;
foreach($targetPath in $targetPaths){
 $targetDirectory=[IO.DirectoryInfo]::new($targetPath);
 $targetAcl=[IO.FileSystemAclExtensions]::GetAccessControl($targetDirectory,[Security.AccessControl.AccessControlSections]::Access);
 $sandboxDenies=@($targetAcl.GetAccessRules($true,$true,[Security.Principal.NTAccount])|Where-Object {$_.IdentityReference.Value.EndsWith('\\CodexSandboxUsers') -and $_.AccessControlType -eq 'Deny'});
 if($sandboxDenies.Count){
  $targetAcl.SetAccessRuleProtection($true,$true);
  foreach($sandboxDenyRule in @($targetAcl.GetAccessRules($true,$true,[Security.Principal.NTAccount])|Where-Object {$_.IdentityReference.Value.EndsWith('\\CodexSandboxUsers') -and $_.AccessControlType -eq 'Deny'})){
   $targetAcl.RemoveAccessRuleSpecific($sandboxDenyRule);
  }
 }
 DENY
 [IO.FileSystemAclExtensions]::SetAccessControl($targetDirectory,$targetAcl);
}""".replace('PAYLOAD',payload)
    deny_script="$targetAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new('CodexSandboxUsers','FullControl','ContainerInherit, ObjectInherit','None','Deny'));" if deny else ''
    script=script.replace('DENY',deny_script)
    encoded=base64.b64encode(script.encode('utf-16le')).decode()
    from .processes import private_environment
    executable=shutil.which('pwsh.exe') or shutil.which('powershell.exe')
    if not executable:
        raise ValueError('Windows sandbox needs the installed PowerShell ACL tools')
    result=subprocess.run([executable,'-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW,env=private_environment())
    if result.returncode:
        error=ValueError('Unable to refresh owned Windows sandbox permissions')
        error.diagnostic={'stderr':result.stderr}
        raise error


def refresh_scope(repository,paths,*,legacy=False):
    return scope_acl(repository,paths,legacy=legacy)


def protect_scope(repository,paths,*,legacy=False):
    return scope_acl(repository,paths,deny=True,legacy=legacy)


class SandboxedHarness:
    def __init__(self,adapter):
        self.adapter=adapter
    def __getattr__(self,name):
        return getattr(self.adapter,name)
    def send(self,handle,message,*,timeout,**kwargs):
        started=time.monotonic()
        with lease(timeout,handle.interrupted.is_set):
            remaining=max(.1,timeout-(time.monotonic()-started))
            try:
                return self.adapter.send(handle,message,timeout=remaining,**kwargs)
            finally:
                runtime=getattr(handle,'runtime_home',None)
                if runtime:
                    protect_scope(handle.repository,[handle.workspace,runtime])
