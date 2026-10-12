"""Completion races, delivery retries and callback scope without provider calls."""
from urllib.error import HTTPError

import pytest

from ai_scientist.workbench.n8n_client import N8nClient
from ai_scientist.workbench.store import StoreConflict
from tests.workbench.test_n8n_workflows import setup, wait_for, repository
from tests.workbench.test_stage_workflows import run_async


def callback_owner(repository):
    owner, project, identity, _, _ = setup(repository)
    owner.client = N8nClient(repository)
    owner.callbacks.client = owner.client
    owner.callbacks.delays = (0, .01, .01)
    owner.store.change(project, identity, lambda s: s.update(status='RUNNING', generation=1))
    return owner, project, identity


URL = 'http://127.0.0.1:5678/webhook-waiting/101/ideation?signature=fixture&wb_generation=1&wb_iteration=0'


@run_async
async def test_completion_before_wait_is_ready_retries_notification_only(repository, monkeypatch):
    owner, project, identity = callback_owner(repository)
    operations, deliveries = [], []
    async def instant(runtime):
        operations.append(runtime.workflow)
    def resume(url, result):
        deliveries.append((url, result))
        if len(deliveries) == 1:
            raise HTTPError(url, 404, 'Wait not ready', {}, None)
    monkeypatch.setattr(owner.steps, 'prepare_idea', instant)
    monkeypatch.setattr(owner.client, 'resume', resume)
    await owner.step(project, identity, 1, 0, 'ideation', '101', URL)
    await wait_for(lambda: owner.store.get(project, identity)['state']['step_jobs']['0:ideation'].get('callback', {}).get('delivery') == 'DELIVERED')
    assert operations == [identity] and len(deliveries) == 2
    assert deliveries[-1][1]['status'] == 'DONE'
    assert 'signature=fixture' not in str(owner.view(project, identity))
    other = URL.replace('/101/', '/102/')
    with pytest.raises(StoreConflict, match='different n8n execution'):
        await owner.step(project, identity, 1, 0, 'ideation', '102', other)
    assert owner.working.admissions == 0
    await owner.close()


@run_async
async def test_delivery_failure_is_visible_and_retry_never_repeats_operation(repository, monkeypatch):
    owner, project, identity = callback_owner(repository)
    operations, received = [], []
    async def instant(runtime):
        operations.append(runtime.workflow)
    def unavailable(*_):
        raise OSError('n8n unavailable')
    monkeypatch.setattr(owner.steps, 'prepare_idea', instant)
    monkeypatch.setattr(owner.client, 'resume', unavailable)
    await owner.step(project, identity, 1, 0, 'ideation', '101', URL)
    await wait_for(lambda: owner.view(project, identity)['n8n']['callback_failed'])
    monkeypatch.setattr(owner.client, 'resume', lambda url, result: received.append(result))
    owner.callbacks.retry(project, identity)
    await wait_for(lambda: received)
    assert len(operations) == 1 and received[0]['status'] == 'DONE'
    await owner.close()


@run_async
@pytest.mark.parametrize('stop', ['pause', 'recover'])
async def test_backend_recovery_and_pause_notify_failure_without_advancing(repository, monkeypatch, stop):
    owner, project, identity = callback_owner(repository)
    received = []
    async def holding(runtime):
        import asyncio
        await asyncio.Event().wait()
    monkeypatch.setattr(owner.steps, 'prepare_idea', holding)
    monkeypatch.setattr(owner.client, 'resume', lambda url, result: received.append(result))
    await owner.step(project, identity, 1, 0, 'ideation', '101', URL)
    if stop == 'pause':
        await owner.pause(project, identity)
    else:
        owner.recover()
    await wait_for(lambda: received)
    assert received[0]['status'] == 'FAILED' and received[0]['generation'] == 1
    assert owner.store.get(project, identity)['state']['status'] == 'PAUSED'
    assert owner.working.admissions == 0
    await owner.close()


@run_async
async def test_completed_job_registration_and_persisted_delivery_recovery(repository, monkeypatch):
    owner, project, identity = callback_owner(repository)
    received = []
    async def instant(runtime):
        pass
    monkeypatch.setattr(owner.steps, 'prepare_idea', instant)
    await owner.step(project, identity, 1, 0, 'ideation')
    await wait_for(lambda: owner.store.get(project, identity)['state']['step_jobs']['0:ideation']['status'] == 'DONE')
    def unavailable(*_):
        raise OSError('n8n unavailable')
    monkeypatch.setattr(owner.client, 'resume', unavailable)
    await owner.step(project, identity, 1, 0, 'ideation', '101', URL)
    await wait_for(lambda: owner.view(project, identity)['n8n']['callback_failed'])
    await owner.callbacks.close()
    from ai_scientist.workbench.n8n_callbacks import StepCallbacks
    owner.callbacks = StepCallbacks(owner.store, owner.client, delays=(0,))
    monkeypatch.setattr(owner.client, 'resume', lambda url, result: received.append(result))
    owner.store.change(project, identity, lambda s: s.update(status='DONE'))
    owner.recover()
    await wait_for(lambda: received)
    assert received[0]['status'] == 'DONE'
    await owner.close()


@pytest.mark.parametrize('url', [
    'https://example.com/webhook-waiting/101/ideation?wb_generation=1&wb_iteration=0',
    'http://127.0.0.1:8000/webhook-waiting/101/ideation?wb_generation=1&wb_iteration=0',
    'http://127.0.0.1:5678/webhook-waiting/102/ideation?wb_generation=1&wb_iteration=0',
    'http://127.0.0.1:5678/webhook-waiting/101/proposal?wb_generation=1&wb_iteration=0',
    'http://127.0.0.1:5678/webhook-waiting/101/ideation?wb_generation=2&wb_iteration=0',
    'http://127.0.0.1:5678/webhook-waiting/101/ideation?wb_generation=1&wb_iteration=1',
    'http://127.0.0.1:5678/webhook-waiting/101/ideation?wb_generation=1&wb_iteration=0#fragment',
])
def test_callback_url_cannot_target_another_service_or_wait(repository, url):
    client = N8nClient(repository)
    with pytest.raises(ValueError):
        client.validate_resume_url(url, '101', 1, 0, 'ideation')
