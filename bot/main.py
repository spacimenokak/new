import asyncio
import os
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from db.database import init_db, AsyncSessionLocal
from bot.handlers import router
from bot.admin_handlers import router as admin_router
# Импортируй свой класс RedisCache
from cache.redis_client import RedisCache 

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Put it into .env (BOT_TOKEN=...)")

    await init_db()
    
    # 1. Создаем экземпляр и подключаемся к Redis
    redis_cache = RedisCache()
    await redis_cache.connect()
    
    bot = Bot(token=BOT_TOKEN)
    # Если бот раньше работал через webhook (например, на хостинге),
    # polling не сможет читать обновления, пока webhook активен.
    print("Сбрасываю webhook (если он был включен)...", flush=True)
    try:
        await asyncio.wait_for(
            bot.delete_webhook(drop_pending_updates=True),
            timeout=10,
        )
    except Exception as e:
        # Не блокируем запуск, но даём понятный лог.
        print(f"Не удалось сбросить webhook: {type(e).__name__}: {e}", flush=True)
    dp = Dispatcher()
    dp.include_router(router)
    dp.include_router(admin_router)

    @dp.update.middleware()
    async def db_middleware(handler, event, data):
        # 2. Добавляем redis_cache в data, чтобы он был доступен в хендлерах
        data["redis_cache"] = redis_cache 
        
        async with AsyncSessionLocal() as session:
            data["session"] = session
            return await handler(event, data)

    print("Бот запущен (polling)...", flush=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())