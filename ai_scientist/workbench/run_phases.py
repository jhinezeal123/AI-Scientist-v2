"""n8n permits each real experiment phase and waits for its completion."""
import asyncio
from dataclasses import dataclass, field
import threading
import time

from .store import StoreConflict

RUN_PHASES = ('draft', 'tuning', 'research', 'ablation', 'single_execution', 'tree_export',
              'multi_seed', 'summary', 'report', 'citations', 'plots', 'vision_plots',
              'writeup', 'vision_paper', 'review')


def enabled(spec, phase):
    if spec.mode != 'training_research':
        return False
    if phase in {'draft', 'tuning', 'research', 'ablation', 'tree_export'}:
        return spec.search.enabled
    if phase == 'single_execution':
        return not spec.search.enabled
    if phase == 'multi_seed':
        return spec.search.enabled and bool(spec.research.seeds)
    if phase == 'writeup':
        return spec.research.writeup != 'none'
    if phase == 'vision_plots':
        return spec.research.vlm and spec.research.writeup != 'none'
    if phase == 'vision_paper':
        return spec.research.vlm
    return bool(getattr(spec.research, phase))


@dataclass
class Phase:
    permit: threading.Event = field(default_factory=threading.Event)
    complete: threading.Event = field(default_factory=threading.Event)
    started: bool = False
    result: dict = field(default_factory=dict)
    error: str = ''


class RunPhases:
    def __init__(self, owner):
        self.owner = owner
        self.store = owner.store
        self.phases = {}
        self.lock = threading.RLock()

    def bind(self, runtime, run):
        state = self.owner.store.get(runtime.project, runtime.workflow)['state']
        return BoundPhases(self, runtime, (runtime.project, runtime.workflow, runtime.generation,
                                          state['iteration'], run))

    def phase(self, key, name):
        with self.lock:
            return self.phases.setdefault((*key, name), Phase())

    async def advance(self, runtime, name):
        if not enabled(runtime.spec, name):
            return {'skipped': True, 'phase_status': 'not_requested'}
        state = self.owner.store.get(runtime.project, runtime.workflow)['state']
        run = state.get('run_id')
        if not run:
            raise StoreConflict('No approved run for this experiment phase')
        bound = self.bind(runtime, run)
        phase = self.phase(bound.key, name)
        phase.permit.set()
        while not phase.complete.is_set():
            runtime.check()
            record = self.owner.working.record(runtime.project, run)
            if record and (record.get('stop_confirmed') or record.get('state') == 'STOPPING'):
                raise StoreConflict('Experiment stopped before completing ' + name)
            await asyncio.sleep(.05)
        if phase.error:
            raise StoreConflict(phase.error)
        return {'skipped': False, 'phase_status': 'completed', 'phase_result': phase.result}


class BoundPhases:
    def __init__(self, owner, runtime, key):
        self.owner, self.runtime, self.key = owner, runtime, key

    def begin(self, name, deadline):
        phase = self.owner.phase(self.key, name)
        while not phase.permit.wait(.1):
            self.runtime.check()
            if time.monotonic() >= deadline:
                raise TimeoutError('Experiment deadline reached while waiting for ' + name)
        self.runtime.check()
        with self.owner.lock:
            if phase.started:
                raise StoreConflict('Experiment phase cannot be executed twice')
            phase.started = True
        self.owner.store.event(self.runtime.project, self.runtime.workflow, name,
                                     'run_phase_started', run_id=self.key[-1])

    def finish(self, name, result=None, error=''):
        phase = self.owner.phase(self.key, name)
        phase.result, phase.error = result or {}, error
        phase.complete.set()
        self.owner.store.event(self.runtime.project, self.runtime.workflow, name,
            'run_phase_failed' if error else 'run_phase_completed', run_id=self.key[-1])

    def perform(self, name, operation, deadline):
        self.begin(name, deadline)
        try:
            result = operation()
            result = result if isinstance(result, dict) else {}
            error = result.get('reason', 'Experiment phase failed') if result.get('status') in {'failed', 'blocked'} else ''
            self.finish(name, result, error)
            if error:
                raise StoreConflict(error)
            return result
        except BaseException as exc:
            phase = self.owner.phase(self.key, name)
            if not phase.complete.is_set():
                self.finish(name, error=str(exc)[:1000] or 'Experiment phase stopped')
            raise
