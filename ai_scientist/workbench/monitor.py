"""Background exact-session observer; never launches agents or submits notebooks."""
import asyncio
import json
import logging
from .monitor_store import MonitorStore
from .submission import ACTIVE,SUCCESS,FAILURE,write_json

IDENTITY=('account','username','kernel_ref','version','kernel_id','script_version_id','session_id')


class IdentityObservationError(ValueError):
    pass


class RunMonitor:
    def __init__(self, submission):
        self.submission=submission;self.store=submission.store
        self.cache=MonitorStore(self.store);self.tasks={};self.closed=False;self.discovery=None

    def start(self):self.discovery=asyncio.create_task(self._discover())

    async def _discover(self):
        while not self.closed:
            try:
                await self._discover_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logging.getLogger(__name__).warning('Monitor discovery retry: %s',type(exc).__name__)
            await asyncio.sleep(2)

    async def _discover_once(self):
        for project in await asyncio.to_thread(self.store.list_projects):
            history=await asyncio.to_thread(self.store.history,project['id'])
            for item in history['runs']:
                key=(project['id'],item['id'])
                task=self.tasks.get(key)
                if task is not None:
                    if not task.done():continue
                    # A failed observer must be eligible for discovery again.
                    if not task.cancelled():task.exception()
                    self.tasks.pop(key)
                run=await asyncio.to_thread(self.store.run,*key)
                if run['state']=='COMPLETED':continue
                identity=json.loads(run['identity_json']) if run['identity_json'] else {}
                if not all(field in identity for field in IDENTITY):continue
                cached=await asyncio.to_thread(self.cache.delta,*key)
                if cached['terminal']:
                    continue
                self.tasks[key]=asyncio.create_task(self._watch(*key,identity))

    async def _watch(self, project_id, run_id, identity):
        delay=4
        while not self.closed:
            try:
                async with self.submission.read_lock:
                    snapshot=await self.submission.call('workbench_monitor_snapshot',
                        {'account':identity['account'],'pinned_identity':{key:identity[key] for key in IDENTITY}},timeout=60)
                    observed=snapshot['identity']
                    if any(observed.get(key)!=identity[key] for key in IDENTITY):
                        raise IdentityObservationError('Pinned monitoring identity mismatch')
                    status=observed.get('status')
                    if status not in ACTIVE|SUCCESS|FAILURE:raise IdentityObservationError('Unknown provider status')
                    if not isinstance(snapshot.get('records'),list) or type(snapshot.get('complete')) is not bool or type(snapshot.get('terminal')) is not bool:
                        raise ValueError('Invalid monitor snapshot')
                    expected_terminal=status in SUCCESS|FAILURE
                    if snapshot['terminal'] != expected_terminal:raise ValueError('Contradictory terminal status')
                    approved=await asyncio.to_thread(self.store.implementation_snapshot,project_id,run_id,read_only=True)
                    identity={**identity,**observed}
                    state='COLLECTING' if status in SUCCESS else 'FAILED' if status in FAILURE else status
                    persisted=await asyncio.to_thread(self.store.submission_observed,project_id,run_id,state,identity)
                    if persisted=='COMPLETED':return
                    root=self.submission.implementation.root(project_id,run_id)
                    await asyncio.to_thread(write_json,root/'remote-identity.json',identity)
                    if snapshot.get('runner_log') is not None:
                        destination=root/'remote-runner.log'
                        if destination.is_symlink():raise ValueError('Linked terminal log evidence')
                        await asyncio.to_thread(destination.write_text,snapshot['runner_log'],encoding='utf-8')
                    # Only stop the observer after durable run identity and evidence writes.
                    await asyncio.to_thread(self.cache.merge,project_id,run_id,snapshot,
                        approved['body']['metric']['name'],approved['body']['metric']['direction'])
                cached=await asyncio.to_thread(self.cache.delta,project_id,run_id)
                if cached['terminal']:
                    return
                delay=4 if status in {'RUNNING'} else min(30,delay*2)
            except asyncio.CancelledError:raise
            except Exception as exc:
                persisted=await asyncio.to_thread(self.store.submission_observed,project_id,run_id,'UNKNOWN',identity,
                    'Chưa xác minh được quan sát Kaggle mới; giữ identity/log cũ, chỉ đọc lại và không gửi lại.')
                if persisted=='COMPLETED':return
                await asyncio.to_thread(self.cache.failed_read,project_id,run_id,
                    f'Chưa xác minh được quan sát mới ({type(exc).__name__}); giữ log đã lưu và thử đọc lại.')
                delay=min(30,delay*2)
            await asyncio.sleep(delay)


    async def close(self):
        self.closed=True
        tasks=[task for task in [self.discovery,*self.tasks.values()] if task is not None]
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
