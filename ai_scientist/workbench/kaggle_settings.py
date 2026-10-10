"""Kaggle Settings: public cache, account mutations and explicit cookie jobs."""
import asyncio
from datetime import datetime, timezone
import json
import time
import threading
import uuid

from .store import StoreConflict


class KaggleProxySettings:
    def __init__(self, working):
        self.working = working
        self.cache = {}
        self.refresh_lock = asyncio.Lock()
        self.mutation_lock = asyncio.Lock()
        self.job = None
        self.task = None
        self.closed = False
        self.cancelled = threading.Event()

    async def _call(self, account, action, arguments=None):
        try:
            if action == 'cookie-check':
                result = await self.working.check_account_cookie(account)
            else:
                result = await asyncio.to_thread(self.working._donor(account).account_admin, action, arguments, self.cancelled)
        except Exception:
            raise StoreConflict('Chưa nhận được kết quả Kaggle; tải lại trạng thái trước khi thử lại') from None
        if result.get('error'):
            raise StoreConflict(result['error'])
        return result

    def _known_runs(self):
        known = []
        for project in self.working.store.list_projects():
            for run in self.working.store.history(project['id'])['runs']:
                full = self.working.store.run(project['id'], run['id'])
                record = self.working.record(project['id'], run['id'])
                identity = json.loads(full['identity_json']) if full.get('identity_json') else {}
                account = (record or {}).get('account') or identity.get('account') or self.working.config.kaggle_account_alias
                try:
                    snapshot = self.working.store.approved_snapshot(project['id'], run['id'])['snapshot']
                except (StoreConflict, ValueError, KeyError):
                    snapshot = {}
                idea = snapshot.get('idea', {})
                descriptor = (record or {}).get('descriptor') or {}
                known.append({'account': account, 'project_id': project['id'], 'project_name': project['name'],
                    'run_id': run['id'], 'run_title': idea.get('title') or idea.get('text', '')[:80] or run['id'][:8],
                    'run_state': run['state'], 'record': record, 'identity': identity,
                    'ref': descriptor.get('notebook_ref') or identity.get('kernel_ref'),
                    'href': f"/?project={project['id']}&view=run&run={run['id']}"})
        return known

    @staticmethod
    def _link_sessions(account, remote, known):
        for session in (remote.get('sessions') or {}).get('sessions', []):
            candidates = []
            for run in known:
                if run['account'] != account:
                    continue
                record, identity = run['record'], run['identity']
                if record:
                    if record['stop_confirmed'] or run['run_state'] == 'QUEUED':
                        continue
                    expected = run['ref'] or remote['username'] + '/ai-scientist-ssh-' + run['run_id'][:12]
                    matches = bool(session.get('ref')) and session['ref'] == expected
                else:
                    provider_id = identity.get('kernel_session_id') or identity.get('session_id')
                    matches = provider_id is not None and str(provider_id) == str(session['kernel_session_id'])
                if matches:
                    candidates.append(run)
            session['workbench'] = ({key: candidates[0][key] for key in
                ('project_id', 'project_name', 'run_id', 'run_title', 'run_state', 'href')} if len(candidates) == 1 else None)
        return remote

    async def _probe(self, account):
        selected = self.working.accounts.require(account)
        try:
            remote = await self._call(account, 'account-overview')
            if remote.get('account') != account or remote.get('username') != selected['username']:
                raise StoreConflict('Kết quả Kaggle không khớp account đã chọn')
            sessions = remote.get('sessions')
            cookie = remote.get('cookie') or {}
            count = sessions.get('total_count') if sessions else None
            readiness = ('needs_login' if cookie.get('status') in {'expired', 'revoked', 'identity_mismatch'}
                         else 'verified_idle' if count == 0 else 'busy' if type(count) is int else 'unavailable')
            self.working.accounts.record_observation(account, {'account': account, 'username': selected['username'],
                'readiness': readiness, 'idle': count == 0, 'active_session_count': count,
                'observed_at': remote['observed_at']})
        except StoreConflict as exc:
            self.working.accounts.unavailable(account)
            remote = {'account': account, 'username': selected['username'], 'cookie': None,
                      'quota': None, 'sessions': None, 'observed_at': datetime.now(timezone.utc).isoformat(),
                      'errors': [str(exc)]}
        self.cache[account] = (time.monotonic(), remote)
        return remote

    async def snapshot(self, refresh=False):
        if not self.working.accounts:
            raise StoreConflict('Chưa cấu hình Kaggle proxy đóng gói')
        async with self.refresh_lock:
            entries = self.working.accounts.list()
            limit = asyncio.Semaphore(3)
            async def load(entry):
                cached = self.cache.get(entry['account'])
                if entry['configured'] and (refresh or not cached or time.monotonic()-cached[0] > 60):
                    # Cookie job owns login and cache updates; ordinary page reads never login.
                    if self.task is None or self.task.done():
                        async with limit:
                            await self._probe(entry['account'])
            await asyncio.gather(*(load(entry) for entry in entries))
            known = await asyncio.to_thread(self._known_runs)
            rows = []
            for entry in self.working.accounts.list():
                cached = self.cache.get(entry['account'])
                remote = json.loads(json.dumps(cached[1])) if cached else {'cookie': None, 'quota': None, 'sessions': None, 'errors': []}
                self._link_sessions(entry['account'], remote, known)
                rows.append({**entry, **remote})
            return {'accounts': rows, 'cookie_job': self.job}

    def start_cookie_check(self, accounts=None):
        if self.closed:
            raise StoreConflict('Backend đang dừng')
        if self.task is not None and not self.task.done():
            raise StoreConflict('Đang kiểm tra cookie; chờ lượt hiện tại hoàn tất')
        entries = self.working.accounts.list()
        keys = accounts or [entry['account'] for entry in entries if entry['configured']]
        for key in keys:
            self.working.accounts.require(key)
        self.job = {'id': uuid.uuid4().hex, 'state': 'running', 'accounts': [
            {'account': key, 'status': 'pending', 'was_expired': None} for key in keys]}
        self.task = asyncio.create_task(self._check_cookies())
        return self.job

    async def _check_cookies(self):
        try:
            for row in self.job['accounts']:
                if self.closed:
                    row.update(status='interrupted', message='Backend đã dừng kiểm tra cookie.')
                    continue
                row['status'] = 'checking'
                try:
                    before = await self._probe(row['account'])
                    invalid = (before.get('cookie') or {}).get('status') in {'expired', 'revoked', 'identity_mismatch'}
                    row['was_expired'] = invalid
                    if invalid:
                        row['status'] = 'renewing'
                        async with self.mutation_lock:
                            row.update(await self._call(row['account'], 'cookie-check'))
                        await self._probe(row['account'])
                    else:
                        row['status'] = 'valid' if (before.get('cookie') or {}).get('status') == 'valid' else 'unavailable'
                except Exception:
                    row.update(status='error', message='Không hoàn tất kiểm tra; kiểm tra kết nối hoặc đăng nhập thủ công.')
            self.job['state'] = 'completed'
        except asyncio.CancelledError:
            self.job['state'] = 'interrupted'
            raise

    async def add(self, arguments):
        async with self.mutation_lock, self.working.planner.lock:
            if self.task is not None and not self.task.done():
                raise StoreConflict('Chờ kiểm tra cookie hoàn tất trước khi thêm account')
            result = await self._call(self.working.config.kaggle_account_alias, 'account-add', arguments)
            selected = self.working.accounts.require(result['account'])
            return {'account': selected, 'cookie_job': self.start_cookie_check([result['account']])}

    async def remove(self, account):
        async with self.mutation_lock, self.working.planner.lock:
            if not any(item['account'] == account for item in self.working.accounts.list()):
                raise ValueError('Account không có trong proxy')
            if self.task is not None and not self.task.done():
                raise StoreConflict('Chờ kiểm tra cookie hoàn tất trước khi xóa account')
            known = await asyncio.to_thread(self._known_runs)
            for run in known:
                if run['account'] != account:
                    continue
                if (run['record'] and not run['record']['stop_confirmed']) or run['run_state'] in {
                        'QUEUED', 'STARTING', 'WORKING', 'STOPPING', 'UNKNOWN', 'SUBMITTING', 'SUBMITTED', 'REMOTE_QUEUED', 'REMOTE_RUNNING'}:
                    raise StoreConflict('Account đang gắn với run chờ/chạy/chưa xác minh dừng; xử lý run đó trước')
            result = await self._call(account, 'account-remove')
            self.cache.pop(account, None)
            self.working.accounts.observations.pop(account, None)
            return result

    async def close(self):
        self.closed = True
        self.cancelled.set()
        if self.task and not self.task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self.task), 3)
            except TimeoutError:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
