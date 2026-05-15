import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from db.database import init_db, AsyncSessionLocal
from bot.handlers import router
from bot.profile_handlers import router as profile_router
from bot.admin_handlers import router as admin_router
from bot.referral_handlers import router as referral_router
from cache.redis_client import RedisCache
from metrics.http_server import start_metrics_server
from mq.publisher import close_event_publisher, get_event_publisher
from storage.s3_client import get_s3_storage

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Put it into .env (BOT_TOKEN=...)")

    await init_db()

    metrics_runner = await start_metrics_server()

    try:
        storage = get_s3_storage()
        await storage.ensure_bucket()
    except Exception as e:
        logging.getLogger(__name__).warning(
            "MinIO недоступен (%s) — фото можно добавить URL вручную", e
        )

    try:
        await get_event_publisher()
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Redis stream publisher недоступен (%s) — события не публикуются", e
        )

    redis_cache = RedisCache()
    await redis_cache.connect()

    bot = Bot(token=BOT_TOKEN)
    print("Сбрасываю webhook (если он был включен)...", flush=True)
    try:
        await asyncio.wait_for(
            bot.delete_webhook(drop_pending_updates=True),
            timeout=10,
        )
    except Exception as e:
        print(f"Не удалось сбросить webhook: {type(e).__name__}: {e}", flush=True)

    dp = Dispatcher()
    dp.include_router(referral_router)
    dp.include_router(router)
    dp.include_router(profile_router)
    dp.include_router(admin_router)

    @dp.update.middleware()
    async def db_middleware(handler, event, data):
        data["redis_cache"] = redis_cache
        async with AsyncSessionLocal() as session:
            data["session"] = session
            return await handler(event, data)

    print("Бот запущен (polling), метрики: /metrics и /health", flush=True)
    try:
        await dp.start_polling(bot)
    finally:
        await redis_cache.redis.aclose()
        await close_event_publisher()
        await metrics_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
