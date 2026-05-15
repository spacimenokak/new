from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from db.crud import get_profile, update_profile, delete_profile
from bot.parse_utils import (
    parse_optional_bio,
    format_profile_public,
    try_parse_registration_gender,
    try_parse_partner_pref_gender,
    PARTNER_AGE_MIN,
    PARTNER_AGE_MAX,
)
from bot.keyboards import (
    gender_registration_kb,
    partner_pref_gender_kb,
    registered_reply_kb,
    BTN_EDIT_MY_PROFILE,
    BTN_DELETE_MY_PROFILE,
)
from bot.profile_menu import profile_edit_fields_kb, profile_delete_confirm_kb
from bot.photo_utils import (
    MAX_PHOTOS,
    parse_photo_urls_field,
    serialize_photo_urls,
    upload_telegram_photo,
)
from cache.redis_client import RedisCache

router = Router()


class EditProfileForm(StatesGroup):
    waiting_value = State()


FIELD_PROMPTS = {
    "name": "Введи новое имя:",
    "age": "Введи возраст числом:",
    "city": "Введи город:",
    "gender": "Пол: «мужской» / «женский» или кнопки ниже.",
    "bio": "Несколько слов о себе (или «-» чтобы очистить):",
    "interests": "Интересы через запятую (или «-» чтобы очистить):",
    "pref_from": f"Минимальный возраст партнёра ({PARTNER_AGE_MIN}–{PARTNER_AGE_MAX}):",
    "pref_to": f"Максимальный возраст партнёра ({PARTNER_AGE_MIN}–{PARTNER_AGE_MAX}), не меньше минимума:",
    "pref_gender": "Кого ищешь: «мужчин», «женщин» или «неважно».",
    "photos": f"Отправь до {MAX_PHOTOS} фото (файлом) или URL через запятую (или «-» чтобы очистить):",
}


async def _is_registered(session: AsyncSession, uid: int) -> bool:
    r = await session.execute(select(User).where(User.telegram_id == uid))
    u = r.scalar_one_or_none()
    return bool(u and u.is_registered)


@router.message(EditProfileForm.waiting_value, F.photo)
async def edit_apply_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    redis_cache: RedisCache,
    bot: Bot,
):
    data = await state.get_data()
    if data.get("edit_field") != "photos":
        return
    uid = message.from_user.id
    url = await upload_telegram_photo(message, bot)
    if not url:
        await message.answer("Не удалось загрузить в S3. Проверь MinIO или введи URL текстом.")
        return
    prof = await get_profile(session, uid)
    existing = parse_photo_urls_field(prof.photo_urls if prof else None)
    existing.append(url)
    await update_profile(session, uid, photo_urls=serialize_photo_urls(existing[:MAX_PHOTOS]))
    await session.commit()
    await redis_cache.set_feed(uid, [])
    await state.clear()
    p = await get_profile(session, uid)
    await message.answer(
        "✅ Фото загружено в S3.\n\n" + (format_profile_public(p) if p else ""),
        reply_markup=registered_reply_kb(),
    )


@router.message(EditProfileForm.waiting_value)
async def edit_apply_value(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    redis_cache: RedisCache,
):
    data = await state.get_data()
    field = data.get("edit_field")
    uid = message.from_user.id
    text = message.text or ""

    if field == "age":
        if not text.isdigit():
            await message.answer("Нужно целое число.")
            return
        await update_profile(session, uid, age=int(text))
    elif field == "pref_from":
        if not text.isdigit():
            await message.answer("Нужно целое число.")
            return
        n = int(text)
        if n < PARTNER_AGE_MIN or n > PARTNER_AGE_MAX:
            await message.answer(f"От {PARTNER_AGE_MIN} до {PARTNER_AGE_MAX}.")
            return
        await update_profile(session, uid, preferred_age_from=n)
    elif field == "pref_to":
        if not text.isdigit():
            await message.answer("Нужно целое число.")
            return
        n = int(text)
        if n < PARTNER_AGE_MIN or n > PARTNER_AGE_MAX:
            await message.answer(f"От {PARTNER_AGE_MIN} до {PARTNER_AGE_MAX}.")
            return
        prof = await get_profile(session, uid)
        lo = prof.preferred_age_from if prof else PARTNER_AGE_MIN
        if n < lo:
            await message.answer(f"Не меньше текущего минимума ({lo}).")
            return
        await update_profile(session, uid, preferred_age_to=n)
    elif field == "gender":
        r = try_parse_registration_gender(text)
        if r is None:
            await message.answer(
                "Не понял. Выбери кнопкой или напиши «мужской» / «женский».",
                reply_markup=gender_registration_kb(),
            )
            return
        g = None if r == "skip" else r
        await update_profile(session, uid, gender=g)
    elif field == "pref_gender":
        pg = try_parse_partner_pref_gender(text)
        if pg is None:
            await message.answer(
                "Напиши «мужчин», «женщин» или «неважно» — или нажми кнопку.",
                reply_markup=partner_pref_gender_kb(),
            )
            return
        await update_profile(session, uid, preferred_gender=pg)
    elif field == "bio":
        await update_profile(session, uid, bio=parse_optional_bio(text))
    elif field == "interests":
        await update_profile(session, uid, interests=parse_optional_bio(text))
    elif field == "photos":
        if text.strip() in ("-", "очистить", "clear"):
            await update_profile(session, uid, photo_urls="")
        else:
            urls = [u.strip() for u in text.replace("\n", ",").split(",") if u.strip()]
            await update_profile(
                session, uid, photo_urls=serialize_photo_urls(urls[:MAX_PHOTOS])
            )
    elif field == "name":
        await update_profile(session, uid, name=text.strip())
        res = await session.execute(select(User).where(User.telegram_id == uid))
        u = res.scalar_one_or_none()
        if u:
            u.name = text.strip()
    elif field == "city":
        await update_profile(session, uid, city=text.strip())
        res = await session.execute(select(User).where(User.telegram_id == uid))
        u = res.scalar_one_or_none()
        if u:
            u.city = text.strip()
    else:
        await message.answer("Неизвестное поле.")
        await state.clear()
        return

    await session.commit()
    await redis_cache.set_feed(uid, [])
    await state.clear()
    p = await get_profile(session, uid)
    await message.answer(
        "✅ Сохранено.\n\n" + (format_profile_public(p) if p else ""),
        reply_markup=registered_reply_kb(),
    )


@router.message(Command("profile", "my_profile", "anketa"))
async def cmd_profile(message: Message, session: AsyncSession):
    uid = message.from_user.id
    if not await _is_registered(session, uid):
        await message.answer("Анкеты ещё нет. Заверши регистрацию: /start")
        return
    p = await get_profile(session, uid)
    if not p:
        await message.answer("Анкеты ещё нет. Заверши регистрацию: /start")
        return
    await message.answer(format_profile_public(p), reply_markup=registered_reply_kb())


@router.message(F.text == BTN_EDIT_MY_PROFILE)
async def text_edit_my_profile(message: Message, session: AsyncSession, state: FSMContext):
    st = await state.get_state()
    if st and str(st).startswith("RegisterForm"):
        await message.answer("Сначала заверши регистрацию — ответь на вопрос бота.")
        return
    uid = message.from_user.id
    if not await _is_registered(session, uid):
        await message.answer("Сначала зарегистрируйся: /start")
        return
    if not await get_profile(session, uid):
        await message.answer("Анкеты нет. Напиши /start.")
        return
    await state.clear()
    await message.answer("Что изменить? Выбери поле:", reply_markup=profile_edit_fields_kb())


@router.message(F.text == BTN_DELETE_MY_PROFILE)
async def text_delete_my_profile(message: Message, session: AsyncSession, state: FSMContext):
    st = await state.get_state()
    if st and str(st).startswith("RegisterForm"):
        await message.answer("Сначала заверши регистрацию — ответь на вопрос бота.")
        return
    uid = message.from_user.id
    if not await _is_registered(session, uid):
        await message.answer("Сначала зарегистрируйся: /start")
        return
    if not await get_profile(session, uid):
        await message.answer("Анкеты нет. Напиши /start.")
        return
    await state.clear()
    await message.answer(
        "Удалить анкету безвозвратно? Все лайки и мэтчи по ней пропадут из поиска.",
        reply_markup=profile_delete_confirm_kb(),
    )


@router.callback_query(F.data == "crud:edit_menu")
async def edit_menu_callback(callback: CallbackQuery):
    await callback.message.answer("Что изменить? Выбери поле:", reply_markup=profile_edit_fields_kb())
    await callback.answer()


@router.callback_query(F.data == "crud:del_confirm")
async def delete_confirm_callback(callback: CallbackQuery):
    await callback.message.answer(
        "Удалить анкету безвозвратно?",
        reply_markup=profile_delete_confirm_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("crud:f:"))
async def edit_pick_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split(":")[-1]
    await state.update_data(edit_field=field)
    await state.set_state(EditProfileForm.waiting_value)
    prompt = FIELD_PROMPTS.get(field, "Введи значение:")
    if field == "gender":
        await callback.message.answer(prompt, reply_markup=gender_registration_kb())
    elif field == "pref_gender":
        await callback.message.answer(prompt, reply_markup=partner_pref_gender_kb())
    else:
        await callback.message.answer(prompt)
    await callback.answer()


@router.callback_query(F.data == "crud:del_yes")
async def delete_yes(callback: CallbackQuery, session: AsyncSession, redis_cache: RedisCache):
    uid = callback.from_user.id
    ok = await delete_profile(session, uid)
    await session.commit()
    await redis_cache.set_feed(uid, [])
    if ok:
        await callback.message.answer(
            "Анкета удалена. Напиши /start, чтобы зарегистрироваться заново.",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await callback.message.answer("Анкета не найдена.", reply_markup=ReplyKeyboardRemove())
    await callback.answer()


@router.callback_query(F.data.in_(("crud:cancel", "crud:cancel_del")))
async def crud_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer("Ок.")