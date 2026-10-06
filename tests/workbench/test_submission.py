import asyncio
import json
from types import SimpleNamespace
import pytest
from ai_scientist.workbench.submission import SubmissionService,decode_result,save_receipt,saved_version
from ai_scientist.workbench.store import StoreConflict
from test_implementation import Runtime,setup


class MCP:
    def __init__(self, username='verified-user', timeout=False, mismatch=False, missing=False, rejected=False):
        self.calls=[]
        self.username=username
        self.timeout=timeout
        self.mismatch=mismatch
        self.missing=missing
        self.rejected=rejected
    async def call_tool(self,name,args):
        self.calls.append((name,args))
        if name=='workbench_launch_readiness':
            data={'eligible':True,'username':self.username,'account':args['account']}
        elif name=='push_notebook':
            if self.rejected:
                return SimpleNamespace(isError=False,structuredContent={'result':'{"error":"push failed (SaveKernel HTTP 499): fixture upstream rejection","via":"token"}'})
            if self.timeout:
                raise TimeoutError('fixture timeout; real submission may already exist')
            meta=json.loads((__import__('pathlib').Path(args['folder'])/'kernel-metadata.json').read_text())
            data={'ref':meta['id'],'versionNumber':1} if not self.missing else {}
        elif name=='workbench_reconcile_run':
            data={'version':1}
        else:
            data={'account':args['account'],'username':self.username,'kernel_ref':args['kernel_ref'],
                  'version':1,'kernel_id':11,'script_version_id':12,'session_id':13,'status':'RUNNING'}
            if self.mismatch:
                data['kernel_ref']='someone/other'
        return SimpleNamespace(isError=False,structuredContent=data)


async def prepared(tmp_path,mcp):
    store,project,run,worker,planner,implementation=setup(tmp_path,Runtime())
    await implementation.start(project,run['id'])
    await planner.task
    config=SimpleNamespace(kaggle_username='verified-user',kaggle_account_alias='selected')
    submission=SubmissionService(implementation,config,mcp)
    return store,project,run,worker,planner,implementation,submission


def test_reconcile_preserves_completed_report_state(tmp_path):
    async def check():
        mcp=MCP()
        store,p,r,w,planner,implementation,s=await prepared(tmp_path,mcp)
        await s.start(p,r['id']);await s.task
        with store.connection(p) as connection:
            connection.execute('UPDATE runs SET state=?,report_path=? WHERE id=?', ('COMPLETED','report.md',r['id']))
        result=await s.reconcile(p,r['id'])
        assert result['state']=='COMPLETED'
        assert store.run(p,r['id'])['state']=='COMPLETED'
        assert store.run(p,r['id'])['report_path']=='report.md'
        assert sum(name=='push_notebook' for name,_ in mcp.calls)==1
        await planner.close();await w.close(1)
    asyncio.run(check())


def test_double_click_exact_identity_and_restart_no_repush(tmp_path):
    async def check():
        mcp=MCP()
        store,p,r,w,planner,implementation,s=await prepared(tmp_path,mcp)
        result=await s.start(p,r['id'])
        assert result['state']=='SUBMITTING'
        duplicate=await s.start(p,r['id'])
        assert duplicate['already_submitted']
        await s.task
        detail=implementation.detail(p,r['id'])
        assert detail['state']=='RUNNING' and detail['identity']['session_id']==13
        assert detail['identity']['submit_attempts']==1
        store.recover_submission()
        await s.start(p,r['id']);await s.reconcile(p,r['id'])
        assert sum(name=='push_notebook' for name,_ in mcp.calls)==1
        await planner.close();await w.close(1)
    asyncio.run(check())


@pytest.mark.parametrize('failure',['timeout','missing','mismatch'])
def test_unknown_read_only_reconciliation(tmp_path,failure):
    async def check():
        mcp=MCP(timeout=failure=='timeout',missing=failure=='missing',mismatch=failure=='mismatch')
        store,p,r,w,planner,implementation,s=await prepared(tmp_path,mcp)
        await s.start(p,r['id']);await s.task
        assert store.run(p,r['id'])['state']=='UNKNOWN'
        store.recover_submission()
        await s.start(p,r['id'])
        mcp.mismatch=False
        assert (await s.reconcile(p,r['id']))['state']=='RUNNING'
        assert sum(name=='push_notebook' for name,_ in mcp.calls)==1
        await planner.close();await w.close(1)
    asyncio.run(check())


@pytest.mark.parametrize('failure',['wrong_account','hash'])
def test_prelaunch_rejects_without_push(tmp_path,failure):
    async def check():
        mcp=MCP(username='other' if failure=='wrong_account' else 'verified-user')
        store,p,r,w,planner,implementation,s=await prepared(tmp_path,mcp)
        if failure=='hash':
            (implementation.root(p,r['id'])/'source/workload.py').write_text('tampered')
        with pytest.raises((ValueError,StoreConflict)):
            await s.start(p,r['id'])
        assert not any(name=='push_notebook' for name,_ in mcp.calls)
        assert store.run(p,r['id'])['identity_json'] is None
        await planner.close();await w.close(1)
    asyncio.run(check())


def test_restart_at_submitting_does_not_repeat_push(tmp_path):
    async def check():
        mcp=MCP()
        store,p,r,w,planner,implementation,s=await prepared(tmp_path,mcp)
        root,bundle,approved,intent=s.prepare(p,r['id'])
        assert store.reserve_submission(p,r['id'],intent)
        store.recover_submission()
        assert store.run(p,r['id'])['state']=='UNKNOWN'
        await s.start(p,r['id'])
        await s.reconcile(p,r['id'])
        assert not any(name=='push_notebook' for name,_ in mcp.calls)
        with pytest.raises(StoreConflict):
            store.submission_observed(p,r['id'],'RUNNING',{**json.loads(store.run(p,r['id'])['identity_json']),'session_id':999})
        await planner.close();await w.close(1)
    asyncio.run(check())


def test_legacy_mcp_json_string_shape_and_error_redaction():
    response=SimpleNamespace(isError=False,structuredContent={'result':'{"versionNumber":1}'})
    assert decode_result(response)['versionNumber']==1
    with pytest.raises(RuntimeError,match='outcome must be reconciled'):
        decode_result(SimpleNamespace(isError=True))


def test_save_acknowledgment_is_bounded_and_redacted():
    receipt=save_receipt({'error':'Bearer KGAT_fixture_secret','versionNumber':1,'invalidArguments':['bad'],'raw':'private payload'})
    assert receipt['error']=='Provider error detail omitted' and 'raw' not in receipt
    assert receipt['invalid_fields']==['invalidArguments']


@pytest.mark.parametrize('prefix',['','/code/','https://www.kaggle.com/code/','https://kaggle.com/code/'])
def test_save_ref_equivalent_spelling(prefix):
    assert saved_version({'ref':prefix+'owner/ailab-fixture','versionNumber':1},'owner/ailab-fixture') == 1
    assert saved_version(save_receipt({'ref':prefix+'owner/ailab-fixture','version_number':1}),'owner/ailab-fixture') == 1


@pytest.mark.parametrize('ref',['/code/other/ailab-fixture','/code/owner/different',
                              'https://example.invalid/code/owner/ailab-fixture',
                              '/code/owner/ailab-fixture?version=2'])
def test_save_ref_mismatch_still_rejected(ref):
    with pytest.raises(ValueError):
        saved_version({'ref':ref,'versionNumber':1},'owner/ailab-fixture')


def test_valid_saved_ack_recovered_read_only_without_source_lookup(tmp_path):
    async def check():
        mcp=MCP()
        store,p,r,w,planner,implementation,s=await prepared(tmp_path,mcp)
        root,bundle,approved,intent=s.prepare(p,r['id'])
        intent['save_acknowledgment']=save_receipt({'ref':'/code/'+intent['kernel_ref'],'versionNumber':1})
        assert store.reserve_submission(p,r['id'],intent)
        store.recover_submission()
        result=await s.reconcile(p,r['id'])
        assert result['state']=='RUNNING' and result['identity']['version']==1
        assert [name for name,_ in mcp.calls]==['workbench_inspect_run']
        await planner.close();await w.close(1)
    asyncio.run(check())


def test_legacy_upstream_499_is_preserved_and_never_retried(tmp_path):
    async def check():
        mcp=MCP(rejected=True)
        store,p,r,w,planner,implementation,s=await prepared(tmp_path,mcp)
        await s.start(p,r['id']);await s.task
        run=store.run(p,r['id'])
        identity=json.loads(run['identity_json'])
        receipt=json.loads((implementation.root(p,r['id'])/'save-receipt.json').read_text())
        assert run['state']=='UNKNOWN' and 'HTTP 499' in run['error']
        assert receipt['error']=='push failed (SaveKernel HTTP 499): fixture upstream rejection'
        assert identity['save_acknowledgment']==receipt
        mcp.mismatch=True
        await s.reconcile(p,r['id'])
        assert 'HTTP 499' in store.run(p,r['id'])['error']
        await s.start(p,r['id'])
        assert sum(name=='push_notebook' for name,_ in mcp.calls)==1
        await planner.close();await w.close(1)
    asyncio.run(check())


def test_old_crlf_bundle_reconciles_against_actual_submitted_lf_text(tmp_path):
    import hashlib
    async def check():
        mcp=MCP()
        store,p,r,w,planner,implementation,s=await prepared(tmp_path,mcp)
        root,bundle,approved,intent=s.prepare(p,r['id'])
        notebook=bundle/'notebook.ipynb'
        text=notebook.read_text(encoding='utf-8')
        notebook.write_bytes(text.replace('\n','\r\n').encode('utf-8'))
        raw_hash=hashlib.sha256(notebook.read_bytes()).hexdigest()
        sent_hash=hashlib.sha256(text.encode('utf-8')).hexdigest()
        assert raw_hash!=sent_hash
        intent.pop('submitted_source_sha256')
        intent['notebook_sha256']=raw_hash
        intent['bundle_hashes']['notebook.ipynb']=raw_hash
        assert store.reserve_submission(p,r['id'],intent)
        store.recover_submission()
        await s.reconcile(p,r['id'])
        args=next(args for name,args in mcp.calls if name=='workbench_reconcile_run')
        assert args['notebook_sha256']==sent_hash
        saved=json.loads(store.run(p,r['id'])['identity_json'])
        assert saved['notebook_sha256']==raw_hash and saved['submitted_source_sha256']==sent_hash
        assert not any(name=='push_notebook' for name,_ in mcp.calls)
        with pytest.raises(StoreConflict,match='submitted_source_sha256'):
            store.submission_observed(p,r['id'],'UNKNOWN',{**saved,'submitted_source_sha256':'0'*64})
        await planner.close();await w.close(1)
    asyncio.run(check())
