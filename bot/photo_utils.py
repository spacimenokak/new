"""Загрузка фото из Telegram в S3."""

from __future__ import annotations

import json
import logging

from aiogram import Bot
from aiogram.types import Message

from storage.s3_client import get_s3_storage
from metrics.prometheus_metrics import S3_UPLOADS_TOTAL

logger = logging.getLogger(__name__)
MAX_PHOTOS = 3


def parse_photo_urls_field(raw: str | None) -> list[str]:
    if not raw:
        return []
    raw = str(raw).strip()
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            return [str(x) for x in data if x] if isinstance(data, list) else []
        except json.JSONDecodeError:
            pass
    return [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]


def serialize_photo_urls(urls: list[str]) -> str | None:
    if not urls:
        return None
    return json.dumps(urls[:MAX_PHOTOS], ensure_ascii=False)


async def upload_telegram_photo(message: Message, bot: Bot) -> str | None:
    if not message.photo:
        return None
    photo = message.photo[-1]
    try:
        file = await bot.get_file(photo.file_id)
        data = await bot.download_file(file.file_path)
        body = data.read() if hasattr(data, "read") else data
        storage = get_s3_storage()
        url = await storage.upload_bytes(body, content_type="image/jpeg")
        S3_UPLOADS_TOTAL.inc()
        return url
    except Exception:
        logger.exception("S3 upload failed for user %s", message.from_user.id)
        return None
