"""Bounded coder and notebook preparation after approval. Never submit or train."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from .bundle import build_bundle, competition_slug
from .code_prompt import coding_prompt
from .journal import Node, Journal, journal_snapshot, restore_journal
from .store import StoreConflict


BUNDLE_FILES = ('notebook.ipynb', 'kernel-metadata.json', 'context.json', 'payload.json', 'checks.json')
ARTIFACT_FILES = (*BUNDLE_FILES, 'source/workload.py', 'journal.json', 'bundle-manifest.json',
                  *(f'attempts/{attempt}/{name}' for attempt in (1, 2) for name in (*BUNDLE_FILES, 'source/workload.py')))


class ImplementationService:
    def __init__(self, planner, config):
        self.planner = planner
        self.store, self.worker, self.bindings = planner.store, planner.worker, planner.bindings
        self.workspace = config.workspace_root
        self.username = getattr(config, 'kaggle_username', None)

    def root(self, project_id, run_id):
        # Validate ownership before deriving a fixed path, never accept client paths.
        self.store.run(project_id, run_id)
        root = self.workspace / '.workbench/projects' / project_id / 'runs' / run_id
        if root.is_symlink() or not root.resolve().is_relative_to(self.workspace.resolve()):
            raise ValueError('Run artifact directory must remain inside the workspace')
        return root

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
                allowed = {'FAILED','COMPLETED','REMOTE_SUCCEEDED','REMOTE_FAILED','COLLECTING'}
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
                      'errors': prior[-2].get('checks', {}).get('errors', []) if len(prior) > 1 and prior[-2].get('checks') else ['Prior attempt interrupted; complete within approved scope']}
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
                    import hashlib
                    for filename in (*BUNDLE_FILES, 'source/workload.py'):
                        manifest[filename] = hashlib.sha256((root / filename).read_bytes()).hexdigest()
                    (root / 'bundle-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
                (root / 'journal.json').write_text(json.dumps(journal_snapshot(journal), ensure_ascii=False, indent=2), encoding='utf-8')
                await asyncio.to_thread(self.store.finish_implementation_attempt, project_id, run_id, attempt,
                                       node.to_dict(), checks, getattr(result, 'session_id', None),
                                       None if checks['pass'] else '; '.join(checks['errors'])[:1000])
                if checks['pass']:
                    return
                if attempt < approved['body']['budget']['coder_calls']:
                    repair = {'previous_source': payload.source, 'errors': checks['errors']}
                    request_id = uuid.uuid4().hex
                    attempt = await asyncio.to_thread(self.store.reserve_implementation, project_id, run_id, request_id, repair=True)
                    continue
                await asyncio.to_thread(self.store.implementation_failed, project_id, run_id,
                                        'Preflight failed; coder budget exhausted: ' + '; '.join(checks['errors']))
                return
            except BaseException as exc:
                error = 'Implementation interrupted; retry explicitly within remaining coder budget' if isinstance(exc, asyncio.CancelledError) else f'Implementation failed ({type(exc).__name__}); attempt consumed, no training or submit'
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
        run = self.store.run(project_id, run_id)
        root = self.root(project_id, run_id)
        run['artifacts'] = [name for name in ARTIFACT_FILES if (root / name).is_file() and not (root / name).is_symlink()]
        run['ready'] = run['state'] == 'PREFLIGHT' and bool(run['attempts']) and bool(run['attempts'][-1]['checks'] and run['attempts'][-1]['checks']['pass'])
        run['coder_budget'] = self.store.implementation_snapshot(project_id, run_id, read_only=True)['body']['budget']['coder_calls']
        approved = self.store.implementation_snapshot(project_id, run_id, read_only=True)
        run['purpose'] = approved['body']['objective']
        run['expected_outputs'] = approved['body']['expected_outputs']
        run['identity'] = json.loads(run.pop('identity_json')) if run['identity_json'] else None
        # The journal node is persisted in SQLite, while UI detail loads source through allowlisted files.
        run.pop('node_json', None)
        return run
