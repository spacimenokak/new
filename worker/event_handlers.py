"""Обработка событий из Redis Stream (активность по часам, метрики, пересчёт)."""

from __future__ import annotations

import logging
from typing import Any

from metrics.prometheus_metrics import (
    CHAT_INIT_TOTAL,
    LIKES_TOTAL,
    MATCHES_TOTAL,
    MQ_EVENTS_CONSUMED,
    SKIPS_TOTAL,
)
from db.database import AsyncSessionLocal
from db.crud import record_activity_hour, recalculate_rating_for_user

logger = logging.getLogger(__name__)


async def handle_event(payload: dict[str, Any]) -> None:
    event_type = payload.get("type", "unknown")
    MQ_EVENTS_CONSUMED.labels(event_type=event_type).inc()

    actor_id = int(payload["actor_id"])
    target_id = payload.get("target_id")
    hour = int(payload.get("hour_utc", 0))

    async with AsyncSessionLocal() as session:
        await record_activity_hour(session, actor_id, hour)
        if target_id is not None:
            await record_activity_hour(session, int(target_id), hour)

        if event_type == "like":
            LIKES_TOTAL.inc()
        elif event_type == "skip":
            SKIPS_TOTAL.inc()
        elif event_type == "match":
            MATCHES_TOTAL.inc()
        elif event_type == "chat_init":
            CHAT_INIT_TOTAL.inc()

        for uid in {actor_id, int(target_id)} if target_id else {actor_id}:
            await recalculate_rating_for_user(session, uid)

        await session.commit()

    logger.info(
        "Redis event processed type=%s actor=%s target=%s hour=%s",
        event_type,
        actor_id,
        target_id,
        hour,
    )
