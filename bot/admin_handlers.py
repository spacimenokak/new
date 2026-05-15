import os

from dotenv import load_dotenv

load_dotenv()

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from db.crud import get_user_stats, get_profile, ban_user
from worker.tasks import recalculate_all_ratings, recalculate_user_rating

router = Router()

def _parse_admin_ids(value: str | None) -> set[int]:
    if not value:
        return set()
    parts = [p.strip() for p in value.split(",")]
    out: set[int] = set()
    for p in parts:
        if not p:
            continue
        try:
            out.add(int(p))
        except ValueError:
            continue
    return out

ADMIN_IDS = _parse_admin_ids(os.getenv("ADMIN_IDS"))


def _is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


@router.message(Command("admin_recalc_all"))
async def admin_recalc_all(message: Message):
    if not _is_admin(message.from_user.id):
        return
    recalculate_all_ratings.delay()
    await message.answer("Задача полного пересчёта рейтингов отправлена в Celery.")


@router.message(Command("admin_recalc"))
async def admin_recalc_one(message: Message):
    if not _is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /admin_recalc <telegram_id>")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("Нужен числовой telegram_id.")
        return
    recalculate_user_rating.delay(uid)
    await message.answer(f"Пересчёт рейтинга для {uid} поставлен в очередь Celery.")


@router.message(F.text == "/admin_stats", F.from_user.id.in_(ADMIN_IDS))
async def admin_stats(message: Message, session: AsyncSession):
    stats = await get_user_stats(session)
    await message.answer(
        f"📊 Статистика:\n"
        f"Пользователей: {stats['total_users']}\n"
        f"Мэтчей: {stats['total_matches']}\n"
        f"Активных сегодня: {stats['active_today']}"
    )

@router.message(F.text.startswith("/admin_user"), F.from_user.id.in_(ADMIN_IDS))
async def admin_user(message: Message, session: AsyncSession):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /admin_user <telegram_id>")
        return
    user_id = int(parts[1])
    profile = await get_profile(session, user_id)
    if profile:
        await message.answer(f"👤 {profile.name}, {profile.age}\n{profile.city}\nАктивен: {profile.is_active}")
    else:
        await message.answer("Пользователь не найден")

@router.message(F.text.startswith("/admin_ban"), F.from_user.id.in_(ADMIN_IDS))
async def admin_ban(message: Message, session: AsyncSession):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /admin_ban <telegram_id>")
        return
    user_id = int(parts[1])
    ok = await ban_user(session, user_id)
    if ok:
        await session.commit()
        await message.answer(f"Пользователь {user_id} заблокирован")
    else:
        await message.answer("Пользователь не найден")