"""Resume receipt polling from SQLite; never submit or retry a paid request."""
import asyncio
import logging
from fastapi import HTTPException
from sqlmodel import Session, select
from .models import SceneRenderJob
from .plan_api import get_engine

ACTIVE = ('submitting', 'queued', 'running')


async def reconcile_once(after_id=''):
    from .scene_api import poll
    with Session(get_engine()) as session:
        rows = session.exec(select(SceneRenderJob).where(
            SceneRenderJob.status.in_(ACTIVE), SceneRenderJob.id > after_id
        ).order_by(SceneRenderJob.id).limit(20)).all()
        jobs = [(row.blueprint_id, row.id) for row in rows]
    gate = asyncio.Semaphore(4)

    async def check(bid, jid):
        async with gate:
            try:
                await asyncio.wait_for(poll(bid, jid), timeout=45)
            except HTTPException as exc:
                if exc.status_code != 404:
                    logging.getLogger(__name__).warning('Render reconciliation deferred: %s', jid)
            except Exception:
                # Log IDs only: provider exceptions can contain signed URLs.
                logging.getLogger(__name__).warning('Render reconciliation deferred: %s', jid)
    await asyncio.gather(*(check(*job) for job in jobs))
    return jobs[-1][1] if jobs else ''


async def run():
    cursor = ''
    while True:
        try:
            cursor = await reconcile_once(cursor)
        except Exception:
            logging.getLogger(__name__).warning('Render reconciliation scan deferred')
        await asyncio.sleep(5)
