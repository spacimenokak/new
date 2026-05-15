from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from .models import Base
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://dating_user:dating_pass@localhost:5432/dating_db")

_sql_echo = os.getenv("SQL_ECHO", "").lower() in ("1", "true", "yes")
_pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
_max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "5"))

engine = create_async_engine(
    DATABASE_URL,
    echo=_sql_echo,
    pool_pre_ping=True,
    pool_size=_pool_size,
    max_overflow=_max_overflow,
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Индексы под выдачу ленты и подсчёты (этап 4: оптимизация БД)
_STAGE4_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS ix_interactions_actor_id ON interactions(actor_id)",
    "CREATE INDEX IF NOT EXISTS ix_interactions_target_id ON interactions(target_id)",
    "CREATE INDEX IF NOT EXISTS ix_profiles_active_filled ON profiles(is_active, is_filled)",
    "CREATE INDEX IF NOT EXISTS ix_profiles_user_active ON profiles(user_id) WHERE is_active = true AND is_filled = true",
    "CREATE INDEX IF NOT EXISTS ix_ratings_combined_score ON ratings(combined_score DESC NULLS LAST)",
)


async def init_db():
    """Создаёт таблицы и подтягивает колонки в старых БД (create_all не ALTER-ит существующие)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in (
            "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS interests VARCHAR(500)",
            "ALTER TABLE ratings ADD COLUMN IF NOT EXISTS initiated_chats INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE ratings ADD COLUMN IF NOT EXISTS referral_bonus DOUBLE PRECISION NOT NULL DEFAULT 0.0",
            "ALTER TABLE ratings ADD COLUMN IF NOT EXISTS activity_by_hour TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(16)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS invited_by_id BIGINT",
        ):
            await conn.execute(text(stmt))
        for stmt in _STAGE4_INDEX_DDL:
            await conn.execute(text(stmt))

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session