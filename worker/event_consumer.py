"""Consumer событий из Redis Stream (отдельно от списка задач Celery)."""

from __future__ import annotations

import asyncio
import json
import logging
import os

import redis.asyncio as redis
from redis.exceptions import ResponseError
from dotenv import load_dotenv

from mq.publisher import EVENTS_STREAM, _events_redis_url
from worker.event_handlers import handle_event

load_dotenv()

logger = logging.getLogger(__name__)

CONSUMER_GROUP = os.getenv("REDIS_EVENTS_GROUP", "dating-workers")
CONSUMER_NAME = os.getenv("REDIS_EVENTS_CONSUMER", "event-consumer-1")


async def _ensure_group(r: redis.Redis) -> None:
    try:
        await r.xgroup_create(EVENTS_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
        logger.info("Created consumer group %s on %s", CONSUMER_GROUP, EVENTS_STREAM)
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


async def run_consumer() -> None:
    r = await redis.from_url(_events_redis_url(), decode_responses=True)
    await _ensure_group(r)
    logger.info(
        "Redis event consumer started stream=%s group=%s",
        EVENTS_STREAM,
        CONSUMER_GROUP,
    )

    while True:
        try:
            batches = await r.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={EVENTS_STREAM: ">"},
                count=10,
                block=5000,
            )
            if not batches:
                continue

            for _stream, messages in batches:
                for msg_id, fields in messages:
                    try:
                        raw = fields.get("payload") or "{}"
                        payload = json.loads(raw)
                        await handle_event(payload)
                        await r.xack(EVENTS_STREAM, CONSUMER_GROUP, msg_id)
                    except Exception:
                        logger.exception("Failed Redis event %s", msg_id)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Redis consumer loop error")
            await asyncio.sleep(2)

    await r.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_consumer())


if __name__ == "__main__":
    main()
