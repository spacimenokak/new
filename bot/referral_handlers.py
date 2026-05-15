"""Реферальная система: код приглашения и deep-link /start."""

from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from db.crud import ensure_user_referral_code

logger = logging.getLogger(__name__)
router = Router()


def parse_start_ref(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    arg = parts[1].strip()
    if arg.lower().startswith("ref_"):
        return arg[4:].upper()
    if arg.lower().startswith("ref"):
        return arg[3:].lstrip("_").upper()
    return arg.upper()


@router.message(Command("invite"))
async def cmd_invite(message: Message, session: AsyncSession):
    uid = message.from_user.id
    r = await session.execute(select(User).where(User.telegram_id == uid))
    user = r.scalar_one_or_none()
    if not user:
        await message.answer("Сначала напиши /start")
        return

    code = await ensure_user_referral_code(session, user)
    await session.commit()

    me = await message.bot.get_me()
    bot_username = me.username or "your_bot"
    link = f"https://t.me/{bot_username}?start=ref_{code}"
    await message.answer(
        f"Твой код приглашения: {code}\n"
        f"Ссылка для друга:\n{link}\n\n"
        "За каждого друга, завершившего регистрацию по ссылке, "
        f"к комбинированному рейтингу добавляется +{0.05:.2f} (макс. +0.30)."
    )

