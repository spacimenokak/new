"""Фоновые задачи Celery (этап 4: отложенный пересчёт рейтингов)."""

from __future__ import annotations

import asyncio
import logging

from worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(coro):
    """Один event loop на задачу — совместимо с воркером Celery (prefork/solo)."""
    return asyncio.run(coro)


async def _recalculate_user_rating_async(user_id: int) -> None:
    from db.database import AsyncSessionLocal
    from db.crud import recalculate_rating_for_user

    async with AsyncSessionLocal() as session:
        await recalculate_rating_for_user(session, user_id)
        await session.commit()


@celery_app.task(name="worker.tasks.recalculate_user_rating")
def recalculate_user_rating(user_id: int) -> None:
    _run(_recalculate_user_rating_async(user_id))
    logger.info("Celery: recalculate_user_rating done user_id=%s", user_id)


async def _recalculate_all_ratings_async() -> int:
    from db.database import AsyncSessionLocal
    from db.crud import list_profile_user_ids, recalculate_rating_for_user

    async with AsyncSessionLocal() as session:
        ids = await list_profile_user_ids(session)

    for uid in ids:
        async with AsyncSessionLocal() as session:
            await recalculate_rating_for_user(session, uid)
            await session.commit()

    return len(ids)


@celery_app.task(name="worker.tasks.recalculate_all_ratings")
def recalculate_all_ratings() -> int:
    n = _run(_recalculate_all_ratings_async())
    logger.info("Celery: recalculate_all_ratings done count=%s", n)
    return n
