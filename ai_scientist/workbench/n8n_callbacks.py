"""Persist completion delivery independently of research/provider execution."""
import asyncio
from urllib.error import HTTPError


class StepCallbacks:
    def __init__(self, store, client, *, delays=(0, .2, .5, 1, 2, 5, 10, 15, 20, 30)):
        self.store, self.client, self.delays = store, client, delays
        self.tasks = {}

    def schedule(self, project, identity, key):
        job = self.store.get(project, identity)['state'].get('step_jobs', {}).get(key, {})
        callback = job.get('callback')
        if not callback or callback['delivery'] == 'DELIVERED':
            return
        task_key = (project, identity, key, callback['generation'])
        if task_key in self.tasks and not self.tasks[task_key].done():
            return
        self.tasks[task_key] = asyncio.create_task(self._deliver(project, identity, key, dict(callback)))

    def retry(self, project, identity):
        state = self.store.get(project, identity)['state']
        for key, job in state.get('step_jobs', {}).items():
            if job.get('callback') and (job['status'] != 'RUNNING'
                    or job['callback']['generation'] != state['generation']):
                self.schedule(project, identity, key)

    def _update(self, project, identity, key, callback, **fields):
        def update(state):
            registered = state.get('step_jobs', {}).get(key, {}).get('callback')
            if registered and registered['resume_url'] == callback['resume_url']:
                registered.update(fields)
        self.store.change(project, identity, update)

    async def _deliver(self, project, identity, key, callback):
        for delay in self.delays:
            await asyncio.sleep(delay)
            state = self.store.get(project, identity)['state']
            job = state.get('step_jobs', {}).get(key, {})
            if job.get('callback', {}).get('resume_url') != callback['resume_url']:
                return
            if job['callback']['delivery'] == 'DELIVERED':
                return
            if state['generation'] != callback['generation']:
                payload = dict(callback['request'], status='FAILED', failed=True, pending=False,
                               error='Workflow stopped or backend restarted; review before resuming')
            else:
                payload = job.get('view')
                if not payload:
                    return
            self._update(project, identity, key, callback, delivery='PENDING',
                         attempts=job['callback'].get('attempts', 0)+1)
            try:
                await asyncio.to_thread(self.client.resume, callback['resume_url'], payload)
            except (OSError, HTTPError):
                # Includes completion before Wait is ready and n8n downtime.
                # A next-step request confirms receipt if the HTTP response
                # was lost. The canvas verifies generation/iteration as well.
                continue
            self._update(project, identity, key, callback, delivery='DELIVERED')
            return
        self._update(project, identity, key, callback, delivery='FAILED')

    async def close(self):
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
