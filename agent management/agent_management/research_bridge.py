"""Approval-bound outbox into existing research services; never a second run authority."""
from __future__ import annotations

import asyncio
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import uuid

from pydantic import Field

from .bundles import checksum,canonical
from .models import StrictModel
from .store import _json,_now


class ResearchCommand(StrictModel):
    request_id: str = Field(min_length=1,max_length=128)
    project_id: str = Field(min_length=1,max_length=64)
    run_id: str = Field(min_length=1,max_length=128)
    proposal_id: str = Field(min_length=1,max_length=128)
    proposal_version: int = Field(ge=1)
    context_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    scope_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    budget: dict
    review_task_id: str = Field(min_length=1,max_length=128)
    checkpoint: str = Field(pattern=r'^[0-9a-f]{40,64}$')
    accelerator: str = 'cpu'
    ttl_seconds: int = Field(default=600,ge=60,le=43200)
    account: str | None = Field(default=None,max_length=64)


class ResearchBridge:
    def __init__(self,control,projects,working):
        self.control,self.projects,self.working=control,projects,working

    def binding(self,rig_id,run_id):
        rig=self.control.store.rig(rig_id)
        if not rig.project_id:
            raise ValueError('Research team must be bound to a project')
        run=self.projects.run(rig.project_id,run_id)
        approved=self.projects.approved_snapshot(rig.project_id,run_id)
        proposal=next((p for p in self.projects.proposals(rig.project_id) if p['id']==run['proposal_id']),None)
        if proposal is None or proposal['state']!='APPROVED':
            raise ValueError('Human approval is required before a bridge command')
        return {'project_id':rig.project_id,'run_id':run_id,'proposal_id':proposal['id'],
            'proposal_version':proposal['version'],'context_sha256':approved['context_sha256'],
            'scope_sha256':checksum({'body':approved['body'],'snapshot':approved['snapshot']}),
            'budget':approved['body'].get('budget') or {}}

    def verify(self,rig_id,command):
        expected=self.binding(rig_id,command.run_id)
        actual=command.model_dump()
        if any(actual[key]!=value for key,value in expected.items()):
            raise ValueError('Proposal/version/context hash/budget/scope differs from the human approval')
        ceiling=expected['budget'].get('execution_seconds',expected['budget'].get('training_seconds'))
        import math
        if isinstance(ceiling,bool) or not isinstance(ceiling,(int,float)) or not math.isfinite(ceiling) or ceiling<=0:
            raise ValueError('Approved scope needs a positive execution/training budget')
        if command.ttl_seconds>ceiling+120:
            raise ValueError('Session exceeds the approved workload budget plus 120 seconds for collection')
        allowed=expected['budget'].get('accelerators')
        if allowed is not None and command.accelerator not in allowed:
            raise ValueError('Accelerator is outside the approved budget')
        team=self.control.store.snapshot(rig_id)
        tasks={t['id']:t for t in team['tasks']}
        review=tasks.get(command.review_task_id)
        roles={s['id']:s['role'] for s in team['spec']['seats']}
        if review is None or review['state']!='DONE' or roles[review['seat']]!='reviewer' or (review.get('result') or {}).get('checkpoint')!=command.checkpoint:
            raise ValueError('Choose a completed reviewer task at the exact checkpoint')
        chain=[]
        node=review
        while node:
            if node['state']!='DONE' or not node.get('result') or node['payload'].get('kind') not in {'coding','review'}:
                raise ValueError('Review chain contains an unverified coding session')
            if node['state']!='DONE' or not node.get('result') or node['result'].get('checkpoint')!=command.checkpoint:
                # Lead may precede the changed builder checkpoint; it has no code to promote.
                if roles[node['seat']]!='lead':
                    raise ValueError('Review chain has an incomplete or different code checkpoint')
            chain.append(node)
            node=tasks.get(node['depends_on']) if node['depends_on'] else None
            if len(chain)>len(tasks):
                raise ValueError('Invalid task dependency cycle')
        if not {'builder','qa','reviewer'}<={roles[t['seat']] for t in chain}:
            raise ValueError('Research code requires Builder → QA → Reviewer handoff')
        for task in chain:
            session=self.control.store.session(task['result']['session_id'])
            if not (session.get('stop_receipt') or {}).get('tree_stopped'):
                raise ValueError('Team session must have a verified stop receipt')
        builder=next(t for t in chain if roles[t['seat']]=='builder')
        files=builder['result'].get('files',[])
        if sum(len(f['content'].encode()) for f in files)>500000:
            raise ValueError('Reviewed code context exceeds 500KB')
        return {'version':1,'binding':actual,'rig_id':rig_id,'task_ids':[t['id'] for t in reversed(chain)],'files':files}

    def stage(self,manifest):
        binding=manifest['binding']
        root=self.working.view.root(binding['project_id'],binding['run_id'])
        root.mkdir(parents=True,exist_ok=True)
        target=root/'team-provenance.json'
        package={'manifest':manifest,'sha256':checksum(manifest)}
        if target.is_symlink():
            raise ValueError('Refusing linked research provenance file')
        if target.exists():
            if json.loads(target.read_text(encoding='utf-8'))!=package:
                raise ValueError('Run is already bound to a different team command')
        else:
            with target.open('x',encoding='utf-8') as stream:
                stream.write(canonical(package))

    async def dispatch(self,rig_id,command):
        manifest=await asyncio.to_thread(self.verify,rig_id,command)
        binding={**command.model_dump(),'rig_id':rig_id}
        content_hash=checksum(binding)
        owner=uuid.uuid4().hex
        with self.control.store.connect(True) as con:
            row=con.execute('SELECT * FROM outbox WHERE request_id=?',(command.request_id,)).fetchone()
            if row:
                if row['content_hash']!=content_hash:
                    raise ValueError('Research request ID is already bound to different content')
                if row['state']=='DISPATCHED':
                    return json.loads(row['receipt_json'])
                raise ValueError('Research command is active or UNKNOWN; reconcile it before retry')
            con.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?,?,?)',(command.request_id,rig_id,_json(binding),content_hash,'DISPATCHING',command.run_id,None,_now()))
            until=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()
            con.execute('INSERT INTO bridge_claims VALUES(?,?,?)',(command.request_id,owner,until))
            self.control.store.event(con,'research_dispatch_intent',{'binding':binding},rig_id=rig_id,task_id=command.review_task_id,request_id=command.request_id)
        try:
            await asyncio.to_thread(self.stage,manifest)
            # Existing WorkingService owns cookies/admission/2 sessions per account,
            # durable reserve, Kaggle lifecycle, reporting and project state.
            receipt=await self.working.start(command.project_id,command.run_id,
                accelerator=command.accelerator,ttl_seconds=command.ttl_seconds,account=command.account)
        except BaseException:
            with self.control.store.connect(True) as con:
                con.execute("UPDATE outbox SET state='UNKNOWN' WHERE request_id=?",(command.request_id,))
                self.control.store.event(con,'research_reconcile_required',rig_id=rig_id,request_id=command.request_id)
            raise
        with self.control.store.connect(True) as con:
            con.execute("UPDATE outbox SET state='DISPATCHED',receipt_json=? WHERE request_id=?",(_json(receipt),command.request_id))
            con.execute('DELETE FROM bridge_claims WHERE request_id=?',(command.request_id,))
            self.control.store.event(con,'research_dispatched',{'receipt':receipt},rig_id=rig_id,request_id=command.request_id)
        return receipt

    def commands(self,rig_id):
        with self.control.store.connect() as con:
            rows=con.execute('SELECT * FROM outbox WHERE rig_id=? ORDER BY created_at',(rig_id,)).fetchall()
        result=[]
        for row in rows:
            binding=json.loads(row['binding_json'])
            # Read the authoritative project run live; never synchronize run state here.
            run=self.projects.run(binding['project_id'],binding['run_id'])
            result.append({'request_id':row['request_id'],'state':row['state'],'binding':binding,
                'receipt':json.loads(row['receipt_json']) if row['receipt_json'] else None,'run':run})
        return result

    async def reconcile(self,rig_id,request_id,*,retry=False):
        with self.control.store.connect() as con:
            row=con.execute('SELECT * FROM outbox WHERE rig_id=? AND request_id=?',(rig_id,request_id)).fetchone()
        if row is None or row['state']!='UNKNOWN':
            raise ValueError('Only an UNKNOWN research command can be reconciled')
        binding=json.loads(row['binding_json'])
        run=await asyncio.to_thread(self.projects.run,binding['project_id'],binding['run_id'])
        record=await asyncio.to_thread(self.working.record,binding['project_id'],binding['run_id'])
        if record:
            receipt={'run_id':run['id'],'state':run['state'],'reconciled_existing_intent':True}
            with self.control.store.connect(True) as con:
                con.execute("UPDATE outbox SET state='DISPATCHED',receipt_json=? WHERE request_id=?",(_json(receipt),request_id))
                con.execute('DELETE FROM bridge_claims WHERE request_id=?',(request_id,))
                self.control.store.event(con,'research_reconciled',{'receipt':receipt},rig_id=rig_id,request_id=request_id)
            return receipt
        if run['state'] not in {'APPROVED','FAILED','PREFLIGHT'}:
            raise ValueError('Project state does not prove that Working was never reserved')
        receipt={'run_id':run['id'],'working_record_absent':True,'not_dispatched':True}
        if not retry:
            return receipt
        command=ResearchCommand.model_validate({k:v for k,v in binding.items() if k!='rig_id'})
        self.verify(rig_id,command)
        with self.control.store.connect(True) as con:
            # No automatic replay. Explicit human retry, proven no Working intent.
            deleted=con.execute("DELETE FROM outbox WHERE request_id=? AND state='UNKNOWN'",(request_id,))
            if not deleted.rowcount:
                raise ValueError('Research command was reconciled by another request; refresh')
            con.execute('DELETE FROM bridge_claims WHERE request_id=?',(request_id,))
            self.control.store.event(con,'research_retry_authorized',{'receipt':receipt},rig_id=rig_id,request_id=request_id)
        return await self.dispatch(rig_id,command)
