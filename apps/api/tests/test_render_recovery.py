import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlmodel import Session

from app import main, comfy, providers, scene_api, render_worker
from app.config import settings
from app.models import SceneRenderJob, now
from test_plan_api import client


def queued(bid, status='queued', age=0):
    job = SceneRenderJob(blueprint_id=bid, request_key='one', input_hash='test',
        scene_revision=1, plan_revision=1, view_id='view', name='Test', prompt='Style',
        provider_model=comfy.MODEL, status=status, status_url='/api/v2/jobs/test',
        created_at=now() - timedelta(seconds=age))
    with Session(main.engine) as session:
        session.add(job)
        session.commit()
        session.refresh(job)
        return job.id


@pytest.mark.asyncio
async def test_worker_recovers_receipt_without_browser_even_after_restart_delay(client, monkeypatch, tmp_path):
    _, bid = client
    monkeypatch.setattr(settings, 'storage_path', str(tmp_path))
    jid = queued(bid, age=86400)
    folder = scene_api.directory(bid, jid)
    folder.mkdir(parents=True)
    calls = []
    async def poll(_):
        calls.append('poll')
        return 'complete', b'mocked-image'
    async def submit(*args, **kwargs):
        pytest.fail('Recovery must not submit paid work')
    monkeypatch.setattr(comfy, 'poll', poll)
    monkeypatch.setattr(comfy, 'generate', submit)
    assert await render_worker.reconcile_once() == jid
    with Session(main.engine) as session:
        assert session.get(SceneRenderJob, jid).status == 'complete'
    assert (folder / 'result.png').read_bytes() == b'mocked-image'
    await render_worker.reconcile_once()
    assert calls == ['poll']


@pytest.mark.parametrize('code', [429, 500, 503])
def test_transient_polling_failure_keeps_receipt_for_recovery(client, monkeypatch, code):
    c, bid = client
    jid = queued(bid)
    async def poll(_):
        comfy.checked(httpx.Response(code, text='private-data'))
    monkeypatch.setattr(comfy, 'poll', poll)
    result = c.get(f'/blueprints/{bid}/scene/renders/{jid}').json()
    assert result['status'] == 'queued'
    assert 'private-data' not in result['error']
    with Session(main.engine) as session:
        assert session.get(SceneRenderJob, jid).status == 'queued'


@pytest.mark.asyncio
async def test_stale_poll_cannot_downgrade_completed_job(client, monkeypatch):
    _, bid = client
    jid = queued(bid)
    async def poll(_):
        with Session(main.engine) as session:
            job = session.get(SceneRenderJob, jid)
            job.status = 'complete'
            session.add(job)
            session.commit()
        return 'running', None
    monkeypatch.setattr(comfy, 'poll', poll)
    assert (await scene_api.poll(bid, jid))['status'] == 'complete'


@pytest.mark.asyncio
async def test_lost_submission_is_not_retried(client, monkeypatch):
    _, bid = client
    jid = queued(bid, status='submitting', age=1300)
    async def forbidden(*args, **kwargs):
        pytest.fail('Ambiguous submission must not be retried or polled without a receipt')
    monkeypatch.setattr(comfy, 'generate', forbidden)
    monkeypatch.setattr(comfy, 'poll', forbidden)
    await render_worker.reconcile_once()
    with Session(main.engine) as session:
        job = session.get(SceneRenderJob, jid)
        assert job.status == 'failed' and 'dashboard' in job.error


def test_credit_and_auth_errors_are_actionable_and_redacted():
    for code, expected in [(401, 'API server'), (402, 'Add credits'), (403, 'billing status')]:
        with pytest.raises(providers.ProviderUnavailable, match=expected) as error:
            comfy.checked(httpx.Response(code, text='secret-token-and-private-workflow'))
        assert 'secret-token' not in str(error.value)


@pytest.mark.asyncio
async def test_api_lifecycle_starts_and_stops_local_reconciler(monkeypatch):
    from app import dataset_workspace
    events = []
    async def run():
        events.append('started')
        try:
            await asyncio.Future()
        finally:
            events.append('stopped')
    monkeypatch.setattr(settings, 'render_poll_worker_enabled', True)
    monkeypatch.setattr(dataset_workspace, 'recover_restore', lambda: None)
    monkeypatch.setattr(render_worker, 'run', run)
    async with main.lifespan(main.app):
        await asyncio.sleep(0)
        assert events == ['started']
    assert events == ['started', 'stopped']
