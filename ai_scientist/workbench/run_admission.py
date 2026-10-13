"""Review the exact run before admitting a remote session."""
import asyncio
import time


class RunAdmission:
    def __init__(self, owner):
        self.owner = owner

    async def review(self, runtime):
        state = self.owner.store.get(runtime.project, runtime.workflow)['state']
        proposal = next(p for p in self.owner.projects.proposals(runtime.project) if p['id'] == state['proposal_id'])
        return await asyncio.to_thread(runtime.human, 'run_approval',
            {'kind': 'review', 'candidate': {'run_id': state['run_id'], 'proposal': {
             k: proposal[k] for k in ('id', 'version', 'context_sha256', 'body')},
             'account': runtime.spec.account, 'accelerator': runtime.spec.accelerator,
             'ttl_seconds': runtime.spec.ttl_seconds}, 'instruction': 'Approve starting this exact run.'},
            time.monotonic() + 86400, lambda: False)
