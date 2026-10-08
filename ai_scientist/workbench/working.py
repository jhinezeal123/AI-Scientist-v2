"""One user-started Working action: connect, implement, execute, collect, stop."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time

from .journal import Journal, Node, journal_snapshot
from .ssh_terminal import AgentTerminalBridge, DonorSession, collect_files
from .store import StoreConflict
from .kaggle import decode_result
from .working_store import WorkingStore, TERMINAL
from .system_prompt import load_prompt

ACCELERATORS = {'cpu', 'NvidiaT4', 'TpuV5E8', 'TpuV6E8'}
ACTIVE = {'STARTING', 'WORKING', 'STOPPING'}


def sources(approved):
    from urllib.parse import urlsplit
    selected = set(approved['body'].get('data_refs', []))
    competitions, datasets = [], []
    for resource in approved['snapshot']['resources']:
        if resource['id'] not in selected or not resource.get('url'):
            continue
        url = urlsplit(resource['url'])
        if url.hostname not in {'www.kaggle.com', 'kaggle.com'}:
            continue
        parts = url.path.strip('/').split('/')
        if len(parts) >= 2 and parts[0] == 'competitions':
            competitions.append(parts[1])
        if len(parts) >= 3 and parts[0] == 'datasets':
            datasets.append('/'.join(parts[1:3]))
    return sorted(set(competitions)), sorted(set(datasets))


class WorkingService:
    def __init__(self, planner, config, view, mcp, *, donor=None, stop_seconds=120, poll_seconds=3):
        self.planner, self.config, self.view, self.mcp = planner, config, view, mcp
        self.store = planner.store
        self.records = WorkingStore(self.store)
        self.donor = donor or DonorSession(config)
        self.tasks, self.terminals, self.stop_requests = {}, {}, set()
        self.closed = False
        self.stop_seconds = stop_seconds
        self.poll_seconds = poll_seconds

    def record(self, project_id, run_id):
        return self.records.get(project_id, run_id)

    async def check_idle(self):
        """Check known notebooks; unreadable old saves need verified account idleness."""
        observations, unresolved_refs = [], []
        for project in await asyncio.to_thread(self.store.list_projects):
            history = await asyncio.to_thread(self.store.history, project['id'])
            for item in history['runs']:
                if item['state'] in ACTIVE:
                    raise StoreConflict('Working vẫn hoạt động hoặc chưa xác nhận Kaggle đã dừng')
                if item['state'] != 'UNKNOWN':
                    continue
                working = await asyncio.to_thread(self.record, project['id'], item['id'])
                if working and not working['stop_confirmed']:
                    raise StoreConflict('Phiên SSH cũ chưa xác nhận đã dừng')
                run = await asyncio.to_thread(self.store.run, project['id'], item['id'])
                identity = json.loads(run['identity_json']) if run['identity_json'] else {}
                if not identity.get('kernel_ref'):
                    raise StoreConflict('Run UNKNOWN cũ thiếu notebook reference để đối soát')
                try:
                    receipt = await asyncio.to_thread(self.donor.inspect, identity['kernel_ref'])
                except Exception:
                    unresolved_refs.append(identity['kernel_ref'])
                    continue
                if receipt.get('stopped') is not True:
                    raise StoreConflict('Notebook UNKNOWN cũ vẫn đang chạy trên Kaggle')
                observations.append(receipt)
        account_observation = None
        if unresolved_refs:
            # Old ambiguous saves may have no readable notebook. Check all active
            # sessions, including older versions, without altering or replaying it.
            try:
                account_observation = decode_result(await asyncio.wait_for(
                    self.mcp.call_tool('workbench_account_idle', {'account': self.config.kaggle_account_alias}), 60))
            except Exception as exc:
                raise StoreConflict('Chưa xác minh được phiên UNKNOWN cũ hoặc trạng thái toàn account') from exc
            owners = {ref.split('/', 1)[0] for ref in unresolved_refs}
            if (account_observation.get('account') != self.config.kaggle_account_alias
                    or owners != {account_observation.get('username')}
                    or (self.config.kaggle_username and account_observation.get('username') != self.config.kaggle_username)
                    or account_observation.get('idle') is not True
                    or type(account_observation.get('active_session_count')) is not int
                    or account_observation['active_session_count'] != 0
                    or not account_observation.get('observed_at')):
                raise StoreConflict('Account Kaggle chưa xác nhận không có phiên hoạt động; chưa mở phiên mới')
        return {'idle': True, 'account': self.config.kaggle_account_alias,
                'known_notebooks': observations, 'unresolved_notebooks': unresolved_refs,
                'account_observation': account_observation, 'checked_at': datetime.now(timezone.utc).isoformat()}

    async def start(self, project_id, run_id, accelerator=None, ttl_seconds=None):
        accelerator = accelerator or getattr(self.config, 'kaggle_accelerator', 'cpu')
        ttl = ttl_seconds or getattr(self.config, 'kaggle_session_seconds', 1800)
        if accelerator not in ACCELERATORS or type(ttl) is not int or ttl < 60:
            raise ValueError('Chọn CPU, T4 x2 hoặc TPU và thời gian phiên ít nhất 60 giây')
        async with self.planner.lock:
            if self.closed or self.planner.closed or any(not task.done() for task in self.tasks.values()):
                raise StoreConflict('Working đang hoạt động; hoàn tất trước khi mở lượt mới')
            if self.planner.task is not None and not self.planner.task.done():
                raise StoreConflict('Agent đang xử lý yêu cầu khác')
            if self.planner.worker.future is not None and not self.planner.worker.future.done():
                raise StoreConflict('Agent worker đang bận')
            if self.planner.worker.closed or self.planner.worker.state.get('status') == 'unknown':
                raise StoreConflict('Agent worker chưa xác nhận kết thúc lượt trước')
            approved = await asyncio.to_thread(self.store.approved_snapshot, project_id, run_id)
            await asyncio.to_thread(self.store.library(project_id).agent_snapshot, approved['snapshot'])
            # Validate editable prompt files before opening a paid Kaggle session.
            load_prompt('working.instructions')
            load_prompt('working.agent', workdir=self.view.root(project_id, run_id) / 'working-agent')
            for project in await asyncio.to_thread(self.store.list_projects):
                for item in (await asyncio.to_thread(self.store.history, project['id']))['runs']:
                    if item['id'] == run_id:
                        continue
                    allowed = {'FAILED', 'COMPLETED', 'CANCELLED', 'REMOTE_FAILED', 'REMOTE_SUCCEEDED', 'COLLECTING', 'UNKNOWN'}
                    if item['state'] not in allowed:
                        raise StoreConflict('Một Run khác đang hoạt động')
            await self.check_idle()
            root = self.view.root(project_id, run_id)
            root.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(self.records.reserve, project_id, run_id, accelerator, ttl)
            key = (project_id, run_id)
            self.tasks[key] = asyncio.create_task(self._work(key, approved, accelerator, ttl))
            return {'run_id': run_id, 'state': 'STARTING'}

    async def _connect(self, key, approved, accelerator, ttl):
        project_id, run_id = key
        competitions, datasets = sources(approved)
        arguments = {'account': self.config.kaggle_account_alias, 'request_id': run_id,
                     'accelerator': accelerator, 'ttl_seconds': ttl, 'wait_seconds': 60,
                     'competition_sources': competitions, 'dataset_sources': datasets}
        deadline = time.monotonic() + min(300, ttl)
        while True:
            result = decode_result(await asyncio.wait_for(self.mcp.call_tool('kaggle_ssh_start', arguments), 270))
            if result.get('session_id') != run_id:
                raise ValueError('Kaggle SSH session identity mismatch')
            if self.config.kaggle_username and not result.get('notebook_ref', '').startswith(self.config.kaggle_username + '/'):
                raise ValueError('Kaggle notebook owner mismatch')
            await asyncio.to_thread(self.records.update, project_id, run_id, descriptor=result)
            if result.get('submission_status') == 'NOT_SUBMITTED':
                return result
            if key in self.stop_requests or result.get('ssh_status') == 'READY':
                return result
            if time.monotonic() >= deadline:
                raise TimeoutError('Kaggle chưa mở được SSH trong thời gian chờ')
            arguments = {'account': self.config.kaggle_account_alias, 'session_id': run_id,
                         'wait_seconds': 60}

    def _request(self, key, approved, descriptor, workdir):
        helper = str(Path(sys.executable))
        library = self.store.library(key[0])
        library.stage(approved['snapshot'], workdir)
        agent_approved = {**approved, 'snapshot': library.agent_snapshot(approved['snapshot'])}
        data = {'approved': agent_approved, 'remote_directory': descriptor['remote_directory'],
                'terminal_command': f'& "{helper}" .\\terminal.py' if sys.platform == 'win32' else shlex.quote(helper) + ' ./terminal.py',
                'instructions': load_prompt('working.instructions').split('\n\n')}
        feedback = self.view.root(*key) / 'retry-feedback.json'
        if feedback.is_file() and not feedback.is_symlink():
            data['previous_working'] = json.loads(feedback.read_text(encoding='utf-8'))
        source = self.view.root(*key) / 'source/workload.py'
        if source.is_file() and not source.is_symlink() and source.stat().st_size <= 1_000_000:
            data['previous_source'] = source.read_text(encoding='utf-8')
        (workdir / 'working-request.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return self.planner.bindings.request_type(key[1], 'mvp0_working',
            load_prompt('working.agent', workdir=workdir), workdir,
            timeout_seconds=min(getattr(self.config, 'working_seconds', 900), max(1, descriptor['ttl_seconds'] - 60)),
            max_output_bytes=3_000_000)

    async def _work(self, key, approved, accelerator, ttl):
        project_id, run_id = key
        root = self.view.root(*key)
        terminal, gateway = None, None
        outcome = 'FAILED'
        no_submit = False
        try:
            self.records.append_log(*key, 'Đang mở phiên Kaggle và kết nối SSH…\n', 'backend')
            descriptor = await self._connect(key, approved, accelerator, ttl)
            no_submit = descriptor.get('submission_status') == 'NOT_SUBMITTED'
            if no_submit:
                raise RuntimeError('Kaggle chưa nhận notebook bootstrap')
            if key in self.stop_requests:
                outcome = 'CANCELLED'
                return
            terminal = await asyncio.to_thread(self.donor.open, run_id,
                lambda text: self.records.append_log(*key, text))
            self.terminals[key] = terminal
            from .ssh_terminal import transfer_library_file
            for name, data in self.store.library(project_id).selected_files(approved['snapshot']):
                await asyncio.to_thread(transfer_library_file, terminal, name, data)
            if key in self.stop_requests:
                outcome = 'CANCELLED'
                return
            workdir = root / 'working-agent'
            gateway = await asyncio.to_thread(AgentTerminalBridge, terminal, workdir)
            request = self._request(key, approved, descriptor, workdir)
            self.records.update(*key, state='WORKING', phase='working', agent_called=1)
            self.records.append_log(*key, 'SSH đã sẵn sàng. Agent đang làm việc trong Kaggle.\n', 'backend')
            result, payload = await self.planner.worker.run(request)
            await asyncio.to_thread(gateway.close)
            gateway = None
            if key in self.stop_requests:
                outcome = 'CANCELLED'
                return
            self.records.update(*key, phase='collecting', summary=payload.model_dump())
            manifest = await asyncio.to_thread(collect_files, terminal, root,
                approved['body'].get('budget', {}).get('output_bytes'))
            names = {item['path'] for item in manifest['files']}
            if not set(payload.output_files).issubset(names) or (payload.succeeded and manifest['command_count'] < 1):
                raise ValueError('Agent result does not match verified SSH commands/files')
            (root / 'working-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            self.records.update(*key, manifest=manifest)
            source = root / 'source/workload.py'
            code = source.read_text(encoding='utf-8') if source.is_file() and not source.is_symlink() else ''
            node = Node(plan=json.dumps(approved['body'], ensure_ascii=False), code=code)
            node.is_buggy = not payload.succeeded
            node.analysis = payload.summary
            journal = Journal()
            journal.append(node)
            (root / 'journal.json').write_text(json.dumps(journal_snapshot(journal), ensure_ascii=False, indent=2), encoding='utf-8')
            with self.store.connection(project_id) as connection:
                connection.execute('UPDATE runs SET node_id=?,node_json=?,code_sha256=? WHERE id=?',
                    (node.id, json.dumps(node.to_dict()), hashlib.sha256(code.encode()).hexdigest() if code else None, run_id))
            outcome = 'COMPLETED' if payload.succeeded else 'FAILED'
        except BaseException as exc:
            if key in self.stop_requests or isinstance(exc, asyncio.CancelledError):
                outcome = 'CANCELLED'
            self.records.append_log(*key, f'Working dừng ({type(exc).__name__}). Lệnh và notebook không được tự gửi lại.\n', 'backend')
            record = self.record(*key)
            if record and not record['summary']:
                self.records.update(*key, summary={'succeeded': False, 'summary': f'Working bị gián đoạn ({type(exc).__name__})',
                                                  'limitations': ['Chưa hoàn thành công việc đã duyệt.'], 'output_files': []})
            elif record:
                summary = record['summary']
                summary['limitations'].append(f'Backend chưa xác minh đủ kết quả ({type(exc).__name__}). Xem log Working.')
                self.records.update(*key, summary=summary)
        finally:
            if gateway:
                await asyncio.to_thread(gateway.close)
            if key in self.stop_requests:
                outcome = 'CANCELLED'
            self.records.update(*key, state='STOPPING', phase='stopping', outcome=outcome)
            receipt = None
            if no_submit:
                record = self.record(*key)
                receipt = {'session_id': run_id, 'notebook_ref': record['descriptor']['notebook_ref'],
                           'status': 'not_submitted', 'stopped': True}
            else:
                await self._request_stop(key, terminal)
            if terminal:
                await asyncio.to_thread(terminal.close)
                self.terminals.pop(key, None)
            await self._finish_stop(key, receipt)

    async def _request_stop(self, key, terminal=None):
        self.records.append_log(*key, 'Backend đang dừng phiên Kaggle…\n', 'backend')
        try:
            if terminal and terminal.lock.acquire(blocking=False):
                terminal.lock.release()
                try:
                    await asyncio.to_thread(terminal.request, 'stop')
                    return
                except Exception:
                    pass
            # Recovery/cancellation may need a fresh connection to stop an occupied shell.
            await asyncio.to_thread(self.donor.call, 'stop', key[1])
        except Exception:
            self.records.append_log(*key, 'Chưa gửi được STOP; đang kiểm tra Kaggle. Phiên vẫn có thời hạn tự dừng.\n', 'backend')

    async def _finish_stop(self, key, receipt=None):
        deadline = time.monotonic() + self.stop_seconds
        waiting = False
        while receipt is None and not self.closed:
            try:
                observation = await asyncio.to_thread(self.donor.call, 'status', key[1])
                if observation.get('stopped') is True:
                    receipt = observation
                    break
            except Exception:
                pass
            if time.monotonic() >= deadline and not waiting:
                waiting = True
                self.records.update(*key, state='STOPPING', phase='awaiting_stop',
                    error='Chưa xác nhận Kaggle đã dừng. Backend tiếp tục kiểm tra; chưa đánh dấu hoàn tất.')
            await asyncio.sleep(min(10, self.poll_seconds * 3) if waiting else self.poll_seconds)
        if receipt is None:
            self.records.update(*key, state='STOPPING', phase='awaiting_stop',
                error='Chưa xác nhận Kaggle đã dừng. Backend giữ Run ở trạng thái đang dừng; không đánh dấu hoàn tất.')
            return
        record = self.record(*key)
        root = self.view.root(*key)
        (root / 'working-stop.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        summary = record['summary'] or {'summary': 'User dừng Working trước khi agent hoàn thành.', 'limitations': []}
        outcome = record['outcome'] or 'FAILED'
        lines = ['# Working report', '', '## Tóm tắt từ agent', '', summary['summary'], '',
                 '## Bằng chứng backend', '', f'- Run: {key[1]}',
                 f'- Kết quả Working: {outcome}',
                 f'- Kaggle: {receipt["notebook_ref"]}', f'- Trạng thái phiên: {receipt["status"]}',
                 '- Backend đã xác nhận phiên Kaggle dừng.',
                 f'- Số lệnh SSH: {(record["manifest"] or {}).get("command_count", "chưa thu được")}', '',
                 '## Files đã thu và kiểm tra SHA256', '']
        for item in (record['manifest'] or {}).get('files', []):
            lines.append(f'- {item["path"]} · {item["bytes"]} bytes · {item["sha256"]}')
        lines += ['', '## Giới hạn', '', *('- ' + value for value in summary.get('limitations', []))]
        (root / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.records.append_log(*key, 'Đã xác nhận Kaggle dừng. Kết quả Working đã lưu.\n', 'backend')
        self.records.finish(*key, receipt, outcome, 'report.md')

    async def stop(self, project_id, run_id):
        key = (project_id, run_id)
        record = self.record(*key)
        if record is None:
            raise StoreConflict('Run này chưa mở Working')
        if record['stop_confirmed']:
            return {'run_id': run_id, 'state': self.store.run(*key)['state']}
        self.stop_requests.add(key)
        task = self.tasks.get(key)
        if task and not task.done():
            self.records.update(*key, state='STOPPING', phase='stopping')
            if self.planner.worker.state.get('request_id') == run_id and self.planner.worker.state.get('status') == 'running':
                self.planner.worker.cancelled.set()
            return {'run_id': run_id, 'state': 'STOPPING'}
        self.tasks[key] = asyncio.create_task(self._recover_stop(key))
        return {'run_id': run_id, 'state': 'STOPPING'}

    async def _recover_stop(self, key):
        record = self.record(*key)
        self.records.update(*key, state='STOPPING', phase='stopping', outcome=record['outcome'] or 'FAILED')
        await self._request_stop(key)
        await self._finish_stop(key)

    async def recover(self):
        for project in self.store.list_projects():
            for run in self.store.history(project['id'])['runs']:
                record = self.record(project['id'], run['id'])
                if record and not record['stop_confirmed']:
                    key = (project['id'], run['id'])
                    self.tasks[key] = asyncio.create_task(self._recover_stop(key))

    def detail(self, project_id, run_id):
        detail = self.view.detail(project_id, run_id)
        record = self.record(project_id, run_id)
        detail['execution_mode'] = 'ssh' if record or not detail['identity'] else 'legacy'
        if record:
            descriptor = record['descriptor'] or {}
            detail['working'] = {key: record[key] for key in ('phase', 'accelerator', 'ttl_seconds', 'started_at', 'agent_called', 'stop_confirmed')}
            detail['working']['notebook_ref'] = descriptor.get('notebook_ref')
            detail['working']['summary'] = record['summary']
            detail['can_retry'] = record['stop_confirmed'] and not detail['deleted_at']
            detail['coder_calls'] = record['agent_called']
            root = self.view.root(project_id, run_id)
            for name in ('working-manifest.json', 'working-stop.json', 'report.md'):
                if (root / name).is_file() and not (root / name).is_symlink():
                    detail['artifacts'].append(name)
            for item in (record['manifest'] or {}).get('files', []):
                path = root / item['path']
                if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()):
                    detail['artifacts'].append(item['path'])
            detail['artifacts'] = sorted(set(detail['artifacts']))
        return detail

    def history(self, project_id, include_deleted=False):
        history = self.view.history(project_id, include_deleted=include_deleted)
        for run in history['runs']:
            detail = self.detail(project_id, run['id'])
            run.update(execution_mode=detail['execution_mode'], working=detail.get('working'),
                       artifacts=detail['artifacts'], report_available=detail['report_path'] == 'report.md')
        return history

    async def retry(self, project_id, parent_run_id, request_id):
        self.store.run(project_id, parent_run_id)
        record = self.record(project_id, parent_run_id)
        async with self.planner.lock:
            existing = self.store.retry_run(project_id, parent_run_id, request_id)
            if existing:
                return self.detail(project_id, existing)
            if self.closed or self.planner.closed:
                raise StoreConflict('Backend đang dừng')
            if record and not record['stop_confirmed']:
                raise StoreConflict('Kaggle chưa xác nhận dừng; chưa tạo lượt Working mới')
            unknown_ids = []
            for project in self.store.list_projects():
                for item in self.store.history(project['id'])['runs']:
                    if item['state'] == 'UNKNOWN':
                        unknown_ids.append(item['id'])
                    elif item['state'] not in TERMINAL | {'REMOTE_FAILED', 'REMOTE_SUCCEEDED', 'COLLECTING'}:
                        raise StoreConflict('Một Run khác đang hoạt động; hoàn tất trước khi tạo lượt mới')
            if unknown_ids:
                await self.check_idle()
            run, created = self.store.reserve_retry(project_id, parent_run_id, request_id, tuple(unknown_ids))
            if created:
                root = self.view.root(project_id, run['id'])
                root.mkdir(parents=True, exist_ok=True)
                feedback = {'parent_run_id': parent_run_id, 'summary': record['summary'] if record else None,
                            'log_tail': self.store.retry_feedback(project_id, parent_run_id)}
                previous_root = self.view.root(project_id, parent_run_id)
                previous_sources = {}
                saved = (record['manifest'] or {}).get('files', []) if record else [{'path': 'source/workload.py'}]
                for item in saved:
                    path = previous_root / item['path']
                    if item['path'].startswith('source/') and path.is_file() and not path.is_symlink() and path.stat().st_size <= 1_000_000:
                        try:
                            previous_sources[item['path']] = path.read_text(encoding='utf-8')
                        except UnicodeDecodeError:
                            continue
                feedback['previous_sources'] = previous_sources
                (root / 'retry-feedback.json').write_text(json.dumps(feedback, ensure_ascii=False, indent=2), encoding='utf-8')
            return self.detail(project_id, run['id'])

    async def reconcile(self, project_id, run_id):
        """Read status for a historical notebook; never validate or resubmit it."""
        run = self.store.run(project_id, run_id)
        if self.record(project_id, run_id):
            return await self.stop(project_id, run_id)
        identity = json.loads(run['identity_json']) if run['identity_json'] else {}
        kernel_ref = identity.get('kernel_ref')
        if not kernel_ref:
            raise StoreConflict('Run cũ chưa có notebook Kaggle để đối soát')
        receipt = await asyncio.to_thread(self.donor.inspect, kernel_ref)
        status = str(receipt.get('status', '')).lower()
        if receipt.get('notebook_ref') != kernel_ref:
            raise StoreConflict('Kaggle trả trạng thái của notebook khác')
        if status in {'complete', 'completed'}:
            state = 'REMOTE_SUCCEEDED'
        elif status in {'error', 'failed', 'cancelled', 'canceled'}:
            state = 'REMOTE_FAILED'
        elif receipt.get('stopped') is False:
            state = 'REMOTE_RUNNING'
        else:
            raise StoreConflict('Chưa xác định được trạng thái notebook Kaggle')
        self.store.submission_observed(project_id, run_id, state, {**identity, 'status': status})
        return self.detail(project_id, run_id)

    async def close(self, timeout):
        self.closed = True
        for key, task in list(self.tasks.items()):
            if not task.done():
                self.stop_requests.add(key)
                record = self.record(*key)
                if self.planner.worker.state.get('request_id') == key[1] and self.planner.worker.state.get('status') == 'running':
                    self.planner.worker.cancelled.set()
        running = [task for task in self.tasks.values() if not task.done()]
        if running:
            done, pending = await asyncio.wait(running, timeout=timeout)
            for task in pending:
                task.cancel()
            if pending:
                _, remaining = await asyncio.wait(pending, timeout=2)
                for task in remaining:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if not task.cancelled():
                    task.exception()
        for terminal in list(self.terminals.values()):
            await asyncio.to_thread(terminal.close)
