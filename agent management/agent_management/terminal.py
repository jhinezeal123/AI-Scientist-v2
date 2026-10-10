"""Human terminal commands use OS isolation and the same durable seat/process fence."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import shutil
import threading
import uuid

from .processes import run_process, private_environment, process_identity, ProcessFailure
from .harnesses import SessionHandle
from .workspaces import safe_path


class TerminalAdapter:
    def interrupt(self, handle):
        handle.interrupted.set()


def sandbox_command(executable, workspace, policy, repository, argv, protected=(), *, provider_home=None):
    if not executable or not Path(executable).is_file():
        raise ValueError('Terminal requires an installed Codex OS sandbox; no unrestricted fallback')
    filesystem = {':root':'read',str(workspace.resolve()):'read'}
    # Provider stores and research data never enter the command's readable scope.
    private = [repository / '.workbench/projects',
        Path.home()/'.dsh', Path.home()/'.claude', Path.home()/'.claude.json',
        Path.home()/'.codex/auth.json', Path.home()/'.codex/config.toml', Path.home()/'.codex/sessions',
        repository/'kaggle mcp/profiles', *map(Path,protected)]
    providers=repository/'.workbench/agents/providers'
    runtimes=repository/'.workbench/agents/runtimes'
    private.append(providers)
    if provider_home:
        home=Path(provider_home).resolve(strict=True)
        if home.parent!=runtimes.resolve():
            raise ValueError('Provider runtime home must be inside private packaged storage')
        filesystem[str(runtimes.resolve())]='read'
        private.extend(entry for entry in runtimes.iterdir() if entry.resolve()!=home)
        filesystem[str(home)]='write'
    else:
        private.append(runtimes)
    for entry in workspace.iterdir():
        if entry.name.startswith('.') or entry.name.lower() in {'profiles','credentials.json','kaggle.json','cookies.json','secrets'}:
            private.append(entry)
    worktree_root=repository/'.workbench/agents/worktrees'
    if worktree_root.exists():
        for rig_path in worktree_root.iterdir():
            if workspace.parent!=rig_path:
                private.append(rig_path)
            else:
                private.extend(p for p in rig_path.iterdir() if p!=workspace)
    for path in private:
        if path.exists():
            filesystem[str(path.resolve())]='deny'
    if policy.file_edits:
        for name in policy.allowed_paths:
            path=safe_path(workspace,name)
            # Directory prefixes are explicit write roots, individual files remain files.
            if name.endswith('/'):
                path.mkdir(parents=True,exist_ok=True)
            filesystem[str(path)]='write'
    config='permissions.agent-terminal={filesystem={' + ','.join(json.dumps(k)+'='+json.dumps(v) for k,v in filesystem.items()) + '},network={enabled=' + str(policy.network).lower() + '}}'
    # Provider runtime state has its own writable directory. The ACP session
    # still receives the seat's code directory, whose file policy stays read-only.
    launch_directory=Path(provider_home) if provider_home else workspace
    from .windows_isolation import refresh_scope
    refresh_scope(repository,[workspace,launch_directory])
    return [str(executable),'sandbox','-c',config,'-c','windows.sandbox="elevated"','-P','agent-terminal','-C',str(launch_directory),'--',*argv]


def execute(control, rig_id, seat_id, argv, *, request_id, timeout=30, protected=()):
    from .windows_isolation import lease, protect_scope
    with lease(timeout):
        try:
            return _execute(control,rig_id,seat_id,argv,request_id=request_id,timeout=timeout,protected=protected)
        finally:
            workspace=control.workspaces.path(rig_id,seat_id)
            key=hashlib.sha256(json.dumps([rig_id,seat_id,request_id]).encode()).hexdigest()
            home=control.workspaces.repository/'.workbench/agents/runtimes'/('terminal-'+key)
            if workspace.exists() and home.exists():
                protect_scope(control.workspaces.repository,[workspace,home])


def _execute(control, rig_id, seat_id, argv, *, request_id, timeout=30, protected=()):
    if not argv or len(argv)>32 or any(not isinstance(x,str) or len(x)>4096 or '\0' in x for x in argv):
        raise ValueError('Terminal needs a literal argv array with at most 32 arguments')
    with control.lock:
        rig=control.store.rig(rig_id)
        seat=next((s for s in rig.seats if s.id==seat_id),None)
        if seat is None or not seat.policy.terminal:
            raise ValueError('Enable terminal in this seat policy first')
        if (rig_id,seat_id) in control.active:
            raise ValueError('Seat already has a supervised process')
        executable=shutil.which(argv[0]) or argv[0]
        if not Path(executable).is_file() or Path(executable).suffix.lower() in {'.cmd','.bat','.ps1'}:
            raise ValueError('Use an installed native executable; shell shims are unsupported')
        workspace,_=control.workspaces.ensure(rig_id,seat_id,rig.base_ref)
        native=control.registry.resolve('codex').executable()
        # Read-only seats still need a private writable launcher directory on
        # Windows. A tiny Python shim enters the real seat cwd after OS startup;
        # it does not grant that code directory any additional write permission.
        key=hashlib.sha256(json.dumps([rig_id,seat_id,request_id]).encode()).hexdigest()
        runtime_home=control.workspaces.repository/'.workbench/agents/runtimes'/('terminal-'+key)
        if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (runtime_home,*runtime_home.parents) if p.is_relative_to(control.workspaces.repository)):
            raise ValueError('Refusing linked terminal runtime storage')
        runtime_home.mkdir(parents=True,exist_ok=True)
        import sys
        shim='import json,subprocess,sys; args=json.loads(sys.argv[1]); raise SystemExit(subprocess.run(args, cwd=sys.argv[2], shell=False, stderr=subprocess.STDOUT).returncode)'
        command=sandbox_command(native,workspace,seat.policy,control.workspaces.repository,
            [sys.executable,'-I','-c',shim,json.dumps([str(executable),*argv[1:]]),str(workspace)],protected,provider_home=runtime_home)
        payload={'kind':'terminal','argv':argv,'timeout_seconds':timeout}
        task=control.store.queue.enqueue(rig_id,seat_id,request_id,payload,max_pending=256)
        if task['state'] in {'DONE','FAILED','CANCELLED','UNKNOWN'}:
            snapshot=control.store.snapshot(rig_id)
            cached=next(t for t in snapshot['tasks'] if t['id']==task['id'])
            return {'task_id':task['id'],'state':task['state'],**(cached.get('result') or {})}
        claimed=control.store.queue.claim(rig_id,seat_id,lease_seconds=180)
        if claimed is None or claimed['id']!=task['id']:
            if claimed:
                # This command cannot jump ahead of an existing queue owner.
                with control.store.connect(True) as con:
                    con.execute("UPDATE tasks SET state='PENDING',lease_token=NULL,lease_until=NULL WHERE id=? AND lease_token=?",(claimed['id'],claimed['lease_token']))
            control.store.cancel_pending(rig_id,task['id'])
            raise ValueError('Resolve earlier queued tasks before opening a human terminal')
        session=control.store.begin_session(claimed,'terminal')
        handle=SessionHandle(session,seat,workspace)
        control.active[(rig_id,seat_id)]={'adapter':TerminalAdapter(),'handle':handle,'thread':threading.current_thread()}
    identity={'rig_id':rig_id,'seat_id':seat_id,'task_id':task['id'],'request_id':request_id,'provider_id':'terminal','session_id':session}
    receipt=None
    try:
        env=private_environment()
        temporary=runtime_home/'tmp';temporary.mkdir(exist_ok=True)
        env.update(TEMP=str(temporary),TMP=str(temporary),TMPDIR=str(temporary))
        env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTEST_ADDOPTS':'-p no:cacheprovider'})
        output,receipt=run_process(command,workspace,b'',timeout=timeout,cancelled=handle.interrupted.is_set,env=env,
            emit=lambda text:control.store.publish('terminal_output',{'text':text},**identity),
            started=lambda proc:control.store.process_started(session,proc.pid,process_identity(proc.pid)))
        checkpoint=control.workspaces.checkpoint(workspace,task_id=task['id'])
        result={'summary':'Terminal command completed','output':output.decode('utf-8',errors='replace'),'checkpoint':checkpoint,'receipt':receipt}
        control.store.seat_workspace(rig_id,seat_id,workspace,checkpoint)
        control.store.complete_turn(task['id'],claimed['lease_token'],session,result=result,receipt=receipt)
        return result
    except Exception as exc:
        receipt=getattr(exc,'receipt',None) or receipt
        if receipt is None and control.store.process_record(session) is None:
            receipt={'process_exited':True,'tree_stopped':True,'not_started':True}
        uncertain=not receipt or not receipt.get('tree_stopped')
        control.store.fail_task(task['id'],claimed['lease_token'],error=str(exc),uncertain=uncertain)
        control.store.complete_session(session,state='UNKNOWN' if uncertain else 'FAILED',receipt=receipt or {})
        diagnostic=getattr(exc,'diagnostic',None) or {}
        return {'error':str(exc),'receipt':receipt,'output':'\n'.join(v.decode('utf-8',errors='replace') for v in diagnostic.values())}
    finally:
        with control.lock:
            control.active.pop((rig_id,seat_id),None)
