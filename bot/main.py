import asyncio
import os
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from db.database import init_db, AsyncSessionLocal
from bot.handlers import router
from sqlalchemy.ext.asyncio import AsyncSession

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # Middleware для передачи сессии БД в хендлеры
    @dp.update.middleware()
    async def db_middleware(handler, event, data):
        async with AsyncSessionLocal() as session:
            data["session"] = session
            return await handler(event, data)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())