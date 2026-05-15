"""Публикация доменных событий в Redis Stream (MQ по README)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as redis
from dotenv import load_dotenv

from metrics.prometheus_metrics import MQ_EVENTS_PUBLISHED

load_dotenv()

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
EVENTS_STREAM = os.getenv("REDIS_EVENTS_STREAM", "dating:events")
EVENTS_REDIS_DB = os.getenv("REDIS_EVENTS_DB", "3")


def _events_redis_url() -> str:
    base = REDIS_URL.rsplit("/", 1)[0]
    return f"{base}/{EVENTS_REDIS_DB}"


class EventPublisher:
    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    async def connect(self) -> None:
        self._redis = await redis.from_url(_events_redis_url(), decode_responses=True)
        logger.info("Redis EventPublisher connected stream=%s", EVENTS_STREAM)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self._redis:
            raise RuntimeError("EventPublisher not connected")
        body = json.dumps({**payload, "type": event_type}, ensure_ascii=False)
        await self._redis.xadd(EVENTS_STREAM, {"payload": body})
        MQ_EVENTS_PUBLISHED.labels(event_type=event_type).inc()
        logger.debug("Redis stream event %s %s", event_type, payload)

    async def publish_interaction(
        self,
        kind: str,
        actor_id: int,
        target_id: int,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        await self.publish(
            kind,
            {
                "actor_id": actor_id,
                "target_id": target_id,
                "hour_utc": now.hour,
                "ts": now.isoformat(),
                **(extra or {}),
            },
        )


_publisher: Optional[EventPublisher] = None


async def get_event_publisher() -> EventPublisher:
    global _publisher
    if _publisher is None:
        _publisher = EventPublisher()
        await _publisher.connect()
    return _publisher


async def close_event_publisher() -> None:
    global _publisher
    if _publisher:
        await _publisher.close()
        _publisher = None
