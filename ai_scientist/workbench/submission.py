"""One durable submit intent per approved run; all remote operations go through MCP."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from .bundle import build_bundle, competition_slug
from .implementation import BUNDLE_FILES
from .models import CodePayload
from .store import StoreConflict, canonical


ACTIVE = {'QUEUED','STARTING','RUNNING','NEW_SCRIPT','CANCEL_REQUESTED','ACKNOWLEDGED'}
SUCCESS = {'COMPLETE','COMPLETED','SUCCEEDED'}
FAILURE = {'FAILED','ERROR','CANCELLED','CANCELED','TIMED_OUT'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    if path.is_symlink() or temporary.is_symlink():
        raise ValueError('Linked submission evidence path refused')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def save_receipt(response):
    """Persist bounded provider acknowledgment without raw bodies or credentials."""
    receipt = {}
    for key in ('ref','versionNumber','version_number','kernelId','kernel_id','url','via','error','errorMessage'):
        value = response.get(key)
        if isinstance(value,str):
            value = ' '.join(value.split())[:500]
            if any(marker in value.lower() for marker in ('kgat_','bearer ','cookie','token=')):
                value = 'Provider error detail omitted'
        if value is None or isinstance(value,(str,int,bool)):
            receipt[key] = value
    receipt['invalid_fields'] = [key for key,value in response.items() if key.startswith('invalid') and value]
    return receipt


def decode_result(result):
    if getattr(result, 'isError', False):
        # MCP errors may include provider details; keep credentials/raw errors out of app evidence.
        raise RuntimeError('MCP operation failed; outcome must be reconciled')
    structured = getattr(result, 'structuredContent', None)
    if isinstance(structured, dict):
        # FastMCP wraps primitive string returns; legacy tools return JSON strings.
        if set(structured) == {'result'} and isinstance(structured['result'], str):
            structured = json.loads(structured['result'])
        if isinstance(structured, dict):
            return structured
    content = getattr(result, 'content', [])
    texts = [item.text for item in content if getattr(item, 'type', None) == 'text']
    if len(texts) != 1:
        raise ValueError('Expected one structured MCP response')
    value = json.loads(texts[0])
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError('Expected MCP object response')
    return value


def saved_version(response, expected_ref):
    """Accept only equivalent spellings of this exact Kaggle owner/slug."""
    if response.get('error') or response.get('errorMessage') or response.get('invalid_fields'):
        raise ValueError('Save acknowledgment indicates rejection')
    ref = response.get('ref')
    if not isinstance(ref,str) or ref not in {expected_ref, '/code/'+expected_ref,
                  'https://www.kaggle.com/code/'+expected_ref, 'https://kaggle.com/code/'+expected_ref}:
        raise ValueError('Save response missing exact ref/version')
    version = response.get('versionNumber')
    if version is None:
        version = response.get('version_number')
    elif response.get('version_number') is not None and response['version_number'] != version:
        raise ValueError('Save acknowledgment versions disagree')
    if type(version) is not int or version != 1:
        raise ValueError('Save response missing exact ref/version')
    return version


class SubmissionService:
    def __init__(self, implementation, config, mcp):
        self.implementation = implementation
        self.planner = implementation.planner
        self.store = implementation.store
        self.config = config
        self.mcp = mcp
        self.task = None
        self.read_lock = asyncio.Lock()

    async def call(self, name, arguments, timeout=120):
        return decode_result(await asyncio.wait_for(self.mcp.call_tool(name, arguments), timeout))

    async def check_idle(self):
        try:
            evidence = await self.call('workbench_account_idle', {'account':self.config.kaggle_account_alias}, timeout=30)
        except Exception as exc:
            raise StoreConflict('Chưa xác minh được các phiên Kaggle. Thử lại sau; chưa tạo run hoặc gửi notebook.') from exc
        if (evidence.get('account') != self.config.kaggle_account_alias
                or evidence.get('username') != self.config.kaggle_username
                or evidence.get('idle') is not True
                or type(evidence.get('active_session_count')) is not int
                or evidence['active_session_count'] != 0):
            raise StoreConflict('Account Kaggle còn phiên đang chạy hoặc identity chưa xác minh; chưa cho phép run mới.')
        return evidence

    def prepare(self, project_id, run_id):
        run = self.store.run(project_id, run_id)
        if run['state'] != 'PREFLIGHT' or run['identity_json']:
            raise StoreConflict('Run must pass preflight and have no submission intent')
        approved = self.store.implementation_snapshot(project_id, run_id)
        root = self.implementation.root(project_id, run_id)
        manifest_path = root / 'bundle-manifest.json'
        if manifest_path.is_symlink():
            raise ValueError('Linked bundle manifest refused')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        names = (*BUNDLE_FILES, 'source/workload.py')
        if set(manifest) != set(names):
            raise ValueError('Preflight bundle manifest incomplete')
        for name in names:
            path = root / name
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or sha(path) != manifest[name]:
                raise ValueError('Preflight artifact hash/path mismatch: ' + name)
        if manifest['source/workload.py'] != run['code_sha256']:
            raise ValueError('Source hash differs from saved code')
        payload = CodePayload.model_validate_json((root/'payload.json').read_text(encoding='utf-8'))
        if hashlib.sha256(payload.source.encode('utf-8')).hexdigest() != run['code_sha256']:
            raise ValueError('Payload source differs from approved implementation')
        # Regenerate fixed runner/metadata only, preserving exact coder source/config/context.
        bundle = root/'submit-bundle'
        if bundle.is_symlink() or not bundle.resolve().is_relative_to(root.resolve()):
            raise ValueError('Submission bundle path escapes run')
        for name in (*names,'source','bundle-manifest.json'):
            path = bundle/name
            if path.is_symlink() or not path.resolve().is_relative_to(bundle.resolve()):
                raise ValueError('Linked submission bundle path refused: '+name)
        checks = build_bundle(bundle, run, approved, payload, self.config.kaggle_username)
        if not checks['pass']:
            raise ValueError('Submission bundle preflight failed')
        hashes = {name:sha(bundle/name) for name in names}
        write_json(bundle/'bundle-manifest.json', hashes)
        intent = {'account':self.config.kaggle_account_alias, 'username':self.config.kaggle_username,
                  'kernel_ref':self.config.kaggle_username+'/ailab-'+run_id,
                  'code_sha256':run['code_sha256'], 'context_sha256':approved['context_sha256'],
                  'notebook_sha256':hashes['notebook.ipynb'], 'bundle_hashes':hashes,
                  'submitted_source_sha256':hashlib.sha256((bundle/'notebook.ipynb').read_text(encoding='utf-8').encode('utf-8')).hexdigest(),
                  'submit_attempts':1, 'created_at':datetime.now(timezone.utc).isoformat()}
        return root, bundle, approved, intent

    async def start(self, project_id, run_id):
        async with self.planner.lock:
            run = await asyncio.to_thread(self.store.run, project_id, run_id)
            if run['identity_json']:
                return {'run_id':run_id,'state':run['state'],'already_submitted':True}
            if self.planner.closed or (self.planner.task and not self.planner.task.done()) or (self.task and not self.task.done()):
                raise StoreConflict('Another agent/submission job is active')
            for project in await asyncio.to_thread(self.store.list_projects):
                history = await asyncio.to_thread(self.store.history, project['id'])
                allowed = {'FAILED','COMPLETED','REMOTE_SUCCEEDED','REMOTE_FAILED','COLLECTING'}
                if getattr(self.config, 'allow_new_run_after_idle_check', False):
                    allowed.add('UNKNOWN')
                blocking = next((item for item in history['runs'] if item['id'] != run_id and item['state'] not in allowed), None)
                if blocking:
                    raise StoreConflict(f"Run {blocking['id'][:8]} ({blocking['state']}) đang chặn gửi Kaggle.")
            root,bundle,approved,intent = await asyncio.to_thread(self.prepare, project_id, run_id)
            if getattr(self.config, 'allow_new_run_after_idle_check', False):
                idle = await self.check_idle()
                await asyncio.to_thread(write_json, root/'pre-submit-idle-check.json', idle)
            readiness = await self.call('workbench_launch_readiness', {'account':intent['account'],
                                       'competition_slug':competition_slug(approved['snapshot']),
                                       'kernel_ref':intent['kernel_ref']}, timeout=150)
            await asyncio.to_thread(write_json, root/'launch-readiness.json', readiness)
            if readiness.get('eligible') is not True or readiness.get('username') != intent['username'] or readiness.get('account') != intent['account']:
                raise StoreConflict('Kaggle readiness blocked: ' + str(readiness.get('reason','selected account/permission unverified')))
            # Durable intent BEFORE the only push, including across concurrent app processes.
            if not await asyncio.to_thread(self.store.reserve_submission, project_id, run_id, intent):
                return {'run_id':run_id,'already_submitted':True}
            await asyncio.to_thread(write_json, root/'submission-intent.json', intent)
            self.task = asyncio.create_task(self._submit(project_id,run_id,bundle,approved,intent))
            return {'run_id':run_id,'state':'SUBMITTING'}

    async def _submit(self, project_id, run_id, bundle, approved, intent):
        try:
            # Verify frozen bytes immediately before invoking MCP, never execute source locally.
            for name,expected in intent['bundle_hashes'].items():
                if sha(bundle/name) != expected:
                    raise ValueError('Frozen submission bundle changed')
            response = await self.call('push_notebook', {'account':intent['account'],'folder':str(bundle.resolve()),
                                       'timeout':approved['body']['budget']['training_seconds']}, timeout=330)
            receipt = save_receipt(response)
            await asyncio.to_thread(write_json,bundle.parent/'save-receipt.json',receipt)
            intent = {**intent,'save_acknowledgment':receipt}
            if response.get('error') or response.get('errorMessage') or receipt['invalid_fields']:
                reason = receipt.get('error') or receipt.get('errorMessage') or 'Invalid fields: '+', '.join(receipt['invalid_fields'])
                raise ValueError('Kaggle SaveKernel rejected: '+str(reason))
            version = saved_version(response, intent['kernel_ref'])
            intent = {**intent,'version':version}
            await asyncio.to_thread(self.store.submission_observed,project_id,run_id,'SUBMITTING',intent)
            for attempt in range(3):
                try:
                    await self._inspect(project_id,run_id,intent)
                    return
                except (RuntimeError,ValueError,TimeoutError):
                    if attempt < 2:
                        await asyncio.sleep(2)
            raise RuntimeError('Exact version saved but session identity not yet verified')
        except BaseException as exc:
            detail = str(exc) if isinstance(exc,ValueError) else type(exc).__name__
            message = 'Submission outcome UNKNOWN: '+detail[:500]+'; reconcile read-only, never push again'
            intent = {**intent,'submission_error':message}
            await asyncio.to_thread(self.store.submission_observed,project_id,run_id,'UNKNOWN',intent,message)
            if isinstance(exc, asyncio.CancelledError):
                raise

    async def _inspect(self, project_id, run_id, intent):
        arguments = {key:intent[key] for key in ('account','kernel_ref','version')}
        arguments.update({'expected_'+key:intent[key] for key in ('session_id','kernel_id','script_version_id') if key in intent})
        observation = await self.call('workbench_inspect_run',arguments)
        for key in ('account','username','kernel_ref','version','session_id','kernel_id','script_version_id'):
            if key in intent and observation.get(key) != intent[key]:
                raise ValueError('Pinned identity mismatch: '+key)
        if any(type(observation.get(key)) is not int or observation[key] < 1 for key in ('version','session_id','kernel_id','script_version_id')):
            raise ValueError('Incomplete remote identity')
        status = observation.get('status')
        if status not in ACTIVE | SUCCESS | FAILURE:
            raise ValueError('Unknown remote status')
        identity = {**intent,**observation}
        state = 'COLLECTING' if status in SUCCESS else 'FAILED' if status in FAILURE else status
        state=await asyncio.to_thread(self.store.submission_observed,project_id,run_id,state,identity)
        root = self.implementation.root(project_id,run_id)
        await asyncio.to_thread(write_json,root/'remote-identity.json',identity)
        return {'run_id':run_id,'state':state,'identity':identity}

    async def reconcile(self, project_id, run_id):
        async with self.read_lock:
            run = await asyncio.to_thread(self.store.run,project_id,run_id)
            if run['state'] == 'SUBMITTING' and self.task and not self.task.done():
                raise StoreConflict('Wait for the active submission before reconciling')
            if not run['identity_json']:
                raise StoreConflict('No submission intent to reconcile')
            intent = json.loads(run['identity_json'])
            # Keep the upload failure visible; a failed read must not erase its cause.
            if not intent.get('submission_error') and run.get('error') and not run['error'].startswith('Read-only reconciliation'):
                intent = {**intent,'submission_error':run['error'][:700]}
            try:
                if 'version' not in intent:
                    receipt = intent.get('save_acknowledgment')
                    if receipt:
                        # Recover a validated SaveKernel acknowledgment after interruption
                        # or an older parser rejecting Kaggle's /code/owner/slug spelling.
                        try:
                            version = saved_version(receipt, intent['kernel_ref'])
                        except ValueError:
                            pass
                        else:
                            intent = {**intent, 'version':version}
                            await asyncio.to_thread(self.store.submission_observed,project_id,run_id,'UNKNOWN',intent)
                            return await self._inspect(project_id,run_id,intent)
                    if 'submitted_source_sha256' not in intent:
                        # Older Windows bundles had CRLF file bytes; legacy donor open() sends LF text.
                        # Derive only from the exact frozen file, never replace the original artifact hash.
                        root = self.implementation.root(project_id,run_id)
                        notebook = root/'submit-bundle/notebook.ipynb'
                        if notebook.is_symlink() or not notebook.resolve().is_relative_to(root.resolve()) or sha(notebook) != intent['notebook_sha256']:
                            raise ValueError('Frozen notebook hash/path mismatch during reconciliation')
                        intent = {**intent,'submitted_source_sha256':hashlib.sha256(notebook.read_text(encoding='utf-8').encode('utf-8')).hexdigest()}
                        await asyncio.to_thread(self.store.submission_observed,project_id,run_id,'UNKNOWN',intent)
                    resolved = await self.call('workbench_reconcile_run', {'account':intent['account'],
                                              'kernel_ref':intent['kernel_ref'],'notebook_sha256':intent['submitted_source_sha256']})
                    if type(resolved.get('version')) is not int or resolved['version'] < 1:
                        raise ValueError('Unverified recovered version')
                    intent = {**intent,'version':resolved['version']}
                    await asyncio.to_thread(self.store.submission_observed,project_id,run_id,'UNKNOWN',intent)
                return await self._inspect(project_id,run_id,intent)
            except (RuntimeError,ValueError,TimeoutError) as exc:
                error = 'Read-only reconciliation cannot verify exact identity ('+type(exc).__name__+'); no push performed'
                if intent.get('submission_error'):
                    error = intent['submission_error']+' | '+error
                state=await asyncio.to_thread(self.store.submission_observed,project_id,run_id,'UNKNOWN',intent,error)
                return {'run_id':run_id,'state':state,'error':error}

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)
