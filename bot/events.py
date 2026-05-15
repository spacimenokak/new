"""Публикация доменных событий в Redis Stream после действий в боте."""

from __future__ import annotations

import logging
from typing import Any

from mq.publisher import get_event_publisher

logger = logging.getLogger(__name__)


async def publish_interaction_event(
    kind: str,
    actor_id: int,
    target_id: int | None = None,
    **extra: Any,
) -> None:
    try:
        publisher = await get_event_publisher()
        if target_id is not None:
            await publisher.publish_interaction(kind, actor_id, target_id, extra=extra or None)
        else:
            await publisher.publish(kind, {"actor_id": actor_id, **extra})
    except Exception:
        logger.exception(
            "Не удалось опубликовать событие %s actor=%s target=%s",
            kind,
            actor_id,
            target_id,
        )
