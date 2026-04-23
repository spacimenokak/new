from aiogram import Router, F
from aiogram.types import Message
from db.crud import get_user_stats, get_profile, ban_user

router = Router()
ADMIN_IDS = [123456789]  # Сюда свой telegram_id

@router.message(F.text == "/admin_stats", F.from_user.id.in_(ADMIN_IDS))
async def admin_stats(message: Message, session):
    stats = await get_user_stats(session)
    await message.answer(
        f"📊 Статистика:\n"
        f"Пользователей: {stats['total_users']}\n"
        f"Мэтчей: {stats['total_matches']}\n"
        f"Активных сегодня: {stats['active_today']}"
    )

@router.message(F.text.startswith("/admin_user"), F.from_user.id.in_(ADMIN_IDS))
async def admin_user(message: Message, session):
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
async def admin_ban(message: Message, session):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /admin_ban <telegram_id>")
        return
    user_id = int(parts[1])
    await ban_user(session, user_id)
    await message.answer(f"Пользователь {user_id} заблокирован")