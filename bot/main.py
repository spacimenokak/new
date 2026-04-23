import asyncio
import os
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from db.database import init_db, AsyncSessionLocal
from bot.handlers import router
# Импортируй свой класс RedisCache
from cache.redis_client import RedisCache 

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def main():
    await init_db()
    
    # 1. Создаем экземпляр и подключаемся к Redis
    redis_cache = RedisCache()
    await redis_cache.connect()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    @dp.update.middleware()
    async def db_middleware(handler, event, data):
        # 2. Добавляем redis_cache в data, чтобы он был доступен в хендлерах
        data["redis_cache"] = redis_cache 
        
        async with AsyncSessionLocal() as session:
            data["session"] = session
            return await handler(event, data)

    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())