import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

from ai_scientist.workbench.stage_runtime import StageRuntime
from tests.workbench.test_n8n_workflows import setup, repository


def test_phase_waits_for_n8n_and_duplicate_delivery_does_not_execute_again(repository):
    async def check():
        owner, project, identity, _, _ = setup(repository)
        owner.store.change(project, identity, lambda s: s.update(status='RUNNING', run_id='approved-fixture-run'))
        runtime = StageRuntime(owner, project, identity)
        runtime.spec = runtime.spec.model_copy(update={'mode':'training_research'})
        runtime.spec.search.enabled = True
        gate = owner.run_phases.bind(runtime, 'approved-fixture-run')
        calls = []
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(gate.perform, 'draft', lambda: calls.append('actual draft'), time.monotonic()+10)
            await asyncio.sleep(.1)
            assert calls == []
            result = await owner.run_phases.advance(runtime, 'draft')
            future.result(timeout=2)
            assert calls == ['actual draft'] and result['phase_status'] == 'completed'
            assert await owner.run_phases.advance(runtime, 'draft') == result
        runtime.spec.search.enabled = False
        assert (await owner.run_phases.advance(runtime, 'tuning'))['skipped']
        await owner.close()
    asyncio.run(check())
