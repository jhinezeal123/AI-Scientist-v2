"""User-requested code revisions and notebook preparation. Never submit or train."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from .bundle import build_bundle, competition_slug
from .code_prompt import coding_prompt
from .journal import Node, Journal, journal_snapshot, restore_journal
from .models import CodePayload
from .store import StoreConflict


from .run_view import BUNDLE_FILES, ARTIFACT_FILES, RunView


class ImplementationService:
    def __init__(self, planner, config):
        self.planner = planner
        self.store, self.worker, self.bindings = planner.store, planner.worker, planner.bindings
        self.workspace = config.workspace_root
        self.username = getattr(config, 'kaggle_username', None)
        self.view = RunView(self.store, self.workspace, lambda: self.planner.idle_check is not None)

    def root(self, project_id, run_id):
        return self.view.root(project_id, run_id)

    async def start(self, project_id, run_id):
        async with self.planner.lock:
            if self.planner.closed or (self.planner.task is not None and not self.planner.task.done()):
                raise StoreConflict('An agent job is active')
            approved = await asyncio.to_thread(self.store.implementation_snapshot, project_id, run_id)
            competition_slug(approved['snapshot'])
            if not self.username:
                raise ValueError('Set verified kaggle_username in workbench config')
            if self.worker.closed or self.worker.state.get('status') == 'unknown':
                raise StoreConflict('Runtime unavailable or unknown; reconcile before coding')
            has_unknown = False
            for project in await asyncio.to_thread(self.store.list_projects):
                history = await asyncio.to_thread(self.store.history, project['id'])
                candidates = [item for item in history['runs'] if item['id'] != run_id]
                has_unknown = has_unknown or any(item['state'] == 'UNKNOWN' for item in candidates)
                allowed = {'FAILED','COMPLETED','CANCELLED','REMOTE_SUCCEEDED','REMOTE_FAILED','COLLECTING'}
                if self.planner.idle_check is not None:
                    allowed.add('UNKNOWN')
                blocking = next((item for item in candidates if item['state'] not in allowed), None)
                if blocking:
                    raise StoreConflict(f"Run {blocking['id'][:8]} ({blocking['state']}) đang chặn tạo code cho lượt này.")
            if has_unknown:
                # Check before reserving a coder attempt; failed reads consume no budget.
                evidence = await self.planner.idle_check()
                root = self.root(project_id, run_id)
                root.mkdir(parents=True,exist_ok=True)
                destination = root/'pre-code-idle-check.json'
                if destination.is_symlink():
                    raise StoreConflict('Linked implementation evidence path refused')
                destination.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
            request_id = uuid.uuid4().hex
            attempt = await asyncio.to_thread(self.store.reserve_implementation, project_id, run_id, request_id)
            self.planner.task = asyncio.create_task(self._implement(project_id, run_id, approved, attempt, request_id))
            return {'run_id': run_id, 'state': 'IMPLEMENTING', 'attempt': attempt}

    async def retry(self, project_id, parent_run_id, request_id):
        """Prepare another run from the same approval; the user separately requests code/submit."""
        async with self.planner.lock:
            existing = await asyncio.to_thread(self.store.retry_run, project_id, parent_run_id, request_id)
            if existing:
                return await asyncio.to_thread(self.detail, project_id, existing)
            if self.planner.closed or (self.planner.task is not None and not self.planner.task.done()):
                raise StoreConflict('An agent job is active')
            parent = await asyncio.to_thread(self.store.run, project_id, parent_run_id)
            approved = await asyncio.to_thread(self.store.implementation_snapshot, project_id, parent_run_id, read_only=True)
            competition_slug(approved['snapshot'])
            unknown_ids = []
            for project in await asyncio.to_thread(self.store.list_projects):
                history = await asyncio.to_thread(self.store.history, project['id'])
                unknown_ids.extend(item['id'] for item in history['runs'] if item['state'] == 'UNKNOWN')
                allowed = {'FAILED','COMPLETED','CANCELLED','REMOTE_SUCCEEDED','REMOTE_FAILED','COLLECTING'}
                if self.planner.idle_check is not None:
                    allowed.add('UNKNOWN')
                blocking = next((item for item in history['runs'] if item['state'] not in allowed), None)
                if blocking:
                    raise StoreConflict(f"Run {blocking['id'][:8]} ({blocking['state']}) đang hoạt động; hoàn tất trước khi tạo lượt mới.")
            evidence = await self.planner.idle_check() if unknown_ids else None
            run, created = await asyncio.to_thread(self.store.reserve_retry, project_id, parent_run_id, request_id, tuple(unknown_ids))
            if not created:
                return await asyncio.to_thread(self.detail, project_id, run['id'])
            try:
                await asyncio.to_thread(self._reuse, project_id, run['id'], parent, approved, evidence)
            except Exception as exc:
                failed = await asyncio.to_thread(self.store.run, project_id, run['id'])
                for attempt in failed['attempts']:
                    if attempt['state'] == 'RUNNING':
                        await asyncio.to_thread(self.store.finish_implementation_attempt, project_id, run['id'],
                                               attempt['attempt'], None, None, error='Saved code reuse interrupted')
                await asyncio.to_thread(self.store.implementation_failed, project_id, run['id'],
                                        f'Không khôi phục được code ({type(exc).__name__}); bấm tạo code cho run mới. Run cũ giữ nguyên.')
            return await asyncio.to_thread(self.detail, project_id, run['id'])

    def _reuse(self, project_id, run_id, parent, approved, idle_evidence):
        root = self.root(project_id, run_id)
        root.mkdir(parents=True, exist_ok=True)
        feedback = {'parent_run_id': parent['id'], 'parent_state': parent['state'],
                    'code_sha256': parent['code_sha256'],
                    'error': parent['error'], 'log_tail': self.store.retry_feedback(project_id, parent['id'])}
        if idle_evidence:
            feedback['idle_check'] = idle_evidence
        (root/'retry-feedback.json').write_text(json.dumps(feedback, ensure_ascii=False, indent=2), encoding='utf-8')
        previous_root = self.root(project_id, parent['id'])
        completed = [attempt for attempt in parent['attempts'] if attempt['node']]
        previous = previous_root/'attempts'/str(completed[-1]['attempt']) if completed else previous_root
        payload_path = previous/'payload.json'
        if not payload_path.is_file():
            # Some early diagnostic runs only stored the root bundle.
            payload_path = previous_root/'payload.json'
        if not payload_path.is_file():
            return  # The new approved run can request code even if the old call returned no source.
        if payload_path.is_symlink() or not payload_path.resolve().is_relative_to(previous_root.resolve()) or payload_path.stat().st_size > 1_000_000:
            raise ValueError('Invalid saved code payload path/size')
        payload = CodePayload.model_validate_json(payload_path.read_text(encoding='utf-8'))
        if hashlib.sha256(payload.source.encode('utf-8')).hexdigest() != parent['code_sha256']:
            raise ValueError('Saved source differs from parent run')
        attempt = self.store.reserve_implementation(project_id, run_id, uuid.uuid4().hex, origin='REUSE')
        workdir = root/'attempts'/str(attempt)
        run = self.store.run(project_id, run_id)
        checks = build_bundle(workdir, run, approved, payload, self.username)
        node = Node(plan='Reuse saved code from run '+parent['id'], code=payload.source, step=attempt)
        node.is_buggy = not checks['pass']
        node.analysis = 'User requested a new run with the same approved scope. No Codex call or Kaggle submit.\n' + json.dumps(checks, ensure_ascii=False)
        if checks['pass']:
            for name in BUNDLE_FILES:
                shutil.copyfile(workdir/name, root/name)
            (root/'source').mkdir(exist_ok=True)
            shutil.copyfile(workdir/'source/workload.py', root/'source/workload.py')
            manifest = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in (*BUNDLE_FILES, 'source/workload.py')}
            (root/'bundle-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        journal = Journal()
        journal.append(node)
        (root/'journal.json').write_text(json.dumps(journal_snapshot(journal), ensure_ascii=False, indent=2), encoding='utf-8')
        self.store.finish_implementation_attempt(project_id, run_id, attempt, node.to_dict(), checks,
                                                error=None if checks['pass'] else '; '.join(checks['errors'])[:1000])
        if not checks['pass']:
            self.store.implementation_failed(project_id, run_id, 'Code cũ chưa qua preflight; bấm sửa code: '+ '; '.join(checks['errors']))

    async def _implement(self, project_id, run_id, approved, attempt, request_id):
        root = self.root(project_id, run_id)
        root.mkdir(parents=True, exist_ok=True)
        journal = Journal()
        repair = None
        prior = self.store.run(project_id, run_id)['attempts']
        nodes = [a['node'] for a in prior if a['node']]
        if nodes:
            journal = restore_journal({'nodes': nodes})
            repair = {'previous_source': journal.nodes[-1].code,
                      'errors': prior[-2]['checks']['errors'] if len(prior) > 1 and prior[-2].get('checks') else [],
                      'previous_request_error': prior[-2]['error'] if len(prior) > 1 else None}
            feedback = root/'retry-feedback.json'
            if feedback.is_file() and not feedback.is_symlink() and feedback.stat().st_size <= 100_000:
                repair['previous_execution'] = json.loads(feedback.read_text(encoding='utf-8'))
        while True:
            checks = None
            node = None
            result = None
            try:
                workdir = root / 'attempts' / str(attempt)
                workdir.mkdir(parents=True, exist_ok=True)
                prompt = coding_prompt(approved, repair)
                if os.name == 'nt' and len(subprocess.list2cmdline([prompt]).encode('utf-16-le')) // 2 > 29_000:
                    # Preserve full approved context/source; bypass only the argv size limit.
                    (workdir / 'coding-request.txt').write_text(prompt, encoding='utf-8')
                    prompt = ('You are mvp0_code. Read exactly coding-request.txt in the current working directory '
                              'using a read-only file command, then follow its complete coding request. '
                              'This is the sole file/tool access authorized for this attempt. Do not read any other file, '
                              'execute generated code, write files, access network or call MCP. Return the generic '
                              'envelope with text containing CodePayload JSON and files={}. The request preserves '
                              'the immutable approved scope and prior source/check errors; do not alter that scope.')
                request = self.bindings.request_type(request_id, 'mvp0_code', prompt, workdir,
                                                     timeout_seconds=600, max_output_bytes=600_000)
                result, payload = await self.worker.run(request)
                node = Node(plan=json.dumps(approved['body'], ensure_ascii=False), code=payload.source,
                            parent=journal.nodes[-1] if journal.nodes else None,
                            step=attempt)
                journal.append(node)
                run = await asyncio.to_thread(self.store.run, project_id, run_id)
                checks = await asyncio.to_thread(build_bundle, workdir, run, approved, payload, self.username)
                node.is_buggy = not checks['pass']
                node.analysis = payload.implementation_summary + '\nPreflight: ' + json.dumps(checks, ensure_ascii=False)
                if checks['pass']:
                    for filename in BUNDLE_FILES:
                        shutil.copyfile(workdir / filename, root / filename)
                    (root / 'source').mkdir(exist_ok=True)
                    shutil.copyfile(workdir / 'source/workload.py', root / 'source/workload.py')
                    manifest = {}
                    for filename in (*BUNDLE_FILES, 'source/workload.py'):
                        manifest[filename] = hashlib.sha256((root / filename).read_bytes()).hexdigest()
                    (root / 'bundle-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
                (root / 'journal.json').write_text(json.dumps(journal_snapshot(journal), ensure_ascii=False, indent=2), encoding='utf-8')
                await asyncio.to_thread(self.store.finish_implementation_attempt, project_id, run_id, attempt,
                                       node.to_dict(), checks, getattr(result, 'session_id', None),
                                       None if checks['pass'] else '; '.join(checks['errors'])[:1000])
                if checks['pass']:
                    return
                await asyncio.to_thread(self.store.implementation_failed, project_id, run_id,
                                        'Preflight failed; request another code revision: ' + '; '.join(checks['errors']))
                return
            except BaseException as exc:
                error = 'Implementation interrupted; request another code revision explicitly' if isinstance(exc, asyncio.CancelledError) else f'Implementation failed ({type(exc).__name__}); request logged, no training or submit'
                if isinstance(exc, ValueError) and 'Windows CLI argument limit' in str(exc):
                    error = str(exc)
                try:
                    await asyncio.to_thread(self.store.finish_implementation_attempt, project_id, run_id, attempt,
                                           node.to_dict() if node else None, checks, getattr(result, 'session_id', None), error)
                except StoreConflict:
                    pass
                await asyncio.to_thread(self.store.implementation_failed, project_id, run_id, error)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                return

    def detail(self, project_id, run_id):
        return self.view.detail(project_id, run_id)

    def history(self, project_id):
        return self.view.history(project_id)
