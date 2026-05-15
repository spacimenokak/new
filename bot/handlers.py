import logging
import re

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db.models import User
from db.crud import (
    get_profile,
    create_interaction,
    check_match,
    get_next_profile,
    create_profile,
    ensure_rating,
    recalculate_rating_for_user,
    ensure_user_referral_code,
    apply_referral_on_register,
    set_profile_active,
)
from cache.redis_client import RedisCache
from bot.events import publish_interaction_event
from bot.photo_utils import MAX_PHOTOS, serialize_photo_urls, upload_telegram_photo
from bot.referral_handlers import parse_start_ref
from metrics.prometheus_metrics import FEED_REQUESTS_TOTAL, BOT_ERRORS_TOTAL, REFERRALS_APPLIED
from bot.parse_utils import (
    try_parse_registration_gender,
    try_parse_partner_pref_gender,
    parse_optional_bio,
    format_profile_public,
    PARTNER_AGE_MIN,
    PARTNER_AGE_MAX,
)
from bot.keyboards import (
    get_action_keyboard,
    get_match_keyboard,
    gender_registration_kb,
    partner_pref_gender_kb,
    registered_reply_kb,
    BTN_NEXT_PROFILE,
    BTN_PAUSE_DATING,
    BTN_RESUME_DATING,
)

logger = logging.getLogger(__name__)

_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")

router = Router()


def _telegram_username_for_link(raw: str | None) -> str | None:
    if not raw:
        return None
    u = raw.strip().lstrip("@")
    return u if _USERNAME_RE.match(u) else None


async def format_match_notification(session: AsyncSession, partner_telegram_id: int) -> str:
    """Текст уведомления о мэтче: ссылка через @username, иначе tg:// по числовому Telegram ID."""
    r = await session.execute(select(User).where(User.telegram_id == partner_telegram_id))
    user = r.scalar_one_or_none()
    prof = await get_profile(session, partner_telegram_id)
    display = (prof.name if prof else None) or (user.username if user else None) or "Собеседник"
    lines = ["🎉 У вас мэтч!", f"Партнёр: {display}"]

    un = _telegram_username_for_link(user.username if user else None)
    if un:
        lines.append(f"Открыть в Telegram: https://t.me/{un}")
    else:
        lines.append(
            "У партнёра нет публичного @username — открой чат по ссылке (часто срабатывает в приложении Telegram):"
        )
        lines.append(f"tg://user?id={partner_telegram_id}")
        lines.append(
            "Если ссылка не открывается: попроси у человека ник в настройках приватности или найди по имени в глобальном поиске Telegram."
        )
    return "\n".join(lines)


async def send_match_notifications(bot: Bot, session: AsyncSession, user_a: int, user_b: int) -> None:
    """Пишет обоим пользователям в личку (нужен /start боту у каждого)."""
    for recipient_id, partner_id in ((user_a, user_b), (user_b, user_a)):
        text = await format_match_notification(session, partner_id)
        kb = get_match_keyboard(partner_id)
        try:
            await bot.send_message(recipient_id, text, reply_markup=kb)
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            logger.warning("Match DM to %s failed: %s", recipient_id, e)


class RegisterForm(StatesGroup):
    name = State()
    age = State()
    city = State()
    gender = State()
    bio = State()
    interests = State()
    pref_age_from = State()
    pref_age_to = State()
    pref_gender = State()
    photos = State()


async def _finalize_registration(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    redis_cache: RedisCache,
    data: dict,
):
    telegram_id = message.from_user.id

    try:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one()
        user.name = data["name"]
        user.age = data["age"]
        user.city = data["city"]
        user.is_registered = True

        gender_val = data.get("gender")

        photo_urls = data.get("photo_urls")
        if isinstance(photo_urls, list):
            photo_urls = serialize_photo_urls(photo_urls)

        await create_profile(
            session,
            user_id=telegram_id,
            name=user.name,
            age=user.age,
            city=user.city,
            gender=gender_val,
            bio=data.get("bio"),
            interests=data.get("interests"),
            preferred_gender=data.get("preferred_gender") or "any",
            preferred_age_from=data.get("pref_age_from", PARTNER_AGE_MIN),
            preferred_age_to=data.get("pref_age_to", PARTNER_AGE_MAX),
            photo_urls=photo_urls,
        )

        pending_ref = data.get("pending_ref")
        if pending_ref and await apply_referral_on_register(session, telegram_id, pending_ref):
            REFERRALS_APPLIED.inc()

        await ensure_user_referral_code(session, user)
        await session.commit()
    except IntegrityError:
        logger.exception("Registration DB integrity error user %s", telegram_id)
        await session.rollback()
        await message.answer(
            "Не удалось сохранить анкету (конфликт в базе). Напиши /start — если уже зарегистрирована, открой /profile."
        )
        return
    except Exception:
        logger.exception("Registration DB save failed for user %s", telegram_id)
        await session.rollback()
        await message.answer(
            "Не удалось сохранить анкету в базу. Запусти PostgreSQL (`docker compose up -d`), "
            "перезапусти бота (при старте подтягиваются новые колонки в таблицах) и снова /start."
        )
        return

    await state.clear()

    try:
        prof = await get_profile(session, telegram_id)
        if prof:
            await message.answer(
                "✅ Регистрация завершена!\n\n" + format_profile_public(prof),
                reply_markup=registered_reply_kb(),
            )
        else:
            await message.answer(
                "✅ Регистрация сохранена, но сводку не удалось загрузить. Попробуй /profile.",
                reply_markup=registered_reply_kb(),
            )
    except Exception:
        logger.exception("Registration success message failed user %s", telegram_id)
        await message.answer(
            "✅ Анкета в базе сохранена. Не удалось отправить сводку — открой /profile.",
            reply_markup=registered_reply_kb(),
        )

    try:
        await show_next_profile(message, session, redis_cache)
    except Exception:
        logger.exception("Registration feed failed user %s (often Redis)", telegram_id)
        retry_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить поиск анкет",
                        callback_data="refresh_feed",
                    )
                ]
            ]
        )
        await message.answer(
            "Ленту сейчас не удалось открыть (часто это Redis: запусти `docker compose up -d`). "
            "Анкета уже сохранена — нажми кнопку или команду /next.",
            reply_markup=retry_kb,
        )


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext, redis_cache: RedisCache):
    telegram_id = message.from_user.id
    username = message.from_user.username

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    ref_code = parse_start_ref(message.text)
    if ref_code:
        await state.update_data(pending_ref=ref_code)

    if not user:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.flush()
        await ensure_user_referral_code(session, user)
        await session.commit()
        if ref_code:
            await message.answer(
                "👋 Привет! Ты перешёл по приглашению — после регистрации код будет учтён.\n"
                "Как тебя зовут?"
            )
        else:
            await message.answer("👋 Привет! Давай познакомимся. Как тебя зовут?")
        await state.set_state(RegisterForm.name)
    else:
        if user.username != username:
            user.username = username
            await session.commit()
        if user.is_registered:
            if ref_code:
                ok = await apply_referral_on_register(session, telegram_id, ref_code)
                if ok:
                    await session.commit()
                    REFERRALS_APPLIED.inc()
                    await message.answer("✅ Реферальный код принят.")
                else:
                    await session.rollback()
            await message.answer(
                f"С возвращением, {user.name}!",
                reply_markup=registered_reply_kb(),
            )
            try:
                await show_next_profile(message, session, redis_cache)
            except Exception:
                logger.exception("show_next on /start failed user %s", telegram_id)
                retry_kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🔄 Обновить поиск анкет",
                                callback_data="refresh_feed",
                            )
                        ]
                    ]
                )
                await message.answer(
                    "Ленту сейчас не удалось открыть. Проверь Redis (`docker compose up -d`) или нажми кнопку / напиши /next.",
                    reply_markup=retry_kb,
                )
        else:
            await message.answer("Давай завершим регистрацию. Как тебя зовут?")
            await state.set_state(RegisterForm.name)


@router.message(F.text == BTN_PAUSE_DATING)
async def pause_dating(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    redis_cache: RedisCache,
):
    cur = await state.get_state()
    if cur is not None and str(cur).startswith("RegisterForm"):
        await message.answer("Сначала заверши регистрацию.")
        return

    uid = message.from_user.id
    prof = await get_profile(session, uid)
    if not prof:
        await message.answer("Сначала зарегистрируйся: /start")
        return

    if not prof.is_active:
        await message.answer(
            "Твоя анкета уже скрыта из поиска. Мэтчи на месте.\n"
            f"Чтобы вернуться — нажми «{BTN_RESUME_DATING}»."
        )
        return

    await set_profile_active(session, uid, active=False)
    await session.commit()
    await redis_cache.set_feed(uid, [])
    await message.answer(
        "💤 Анкета скрыта: другие больше не увидят тебя в ленте.\n"
        "Мэтчи и история лайков сохранены.\n\n"
        f"Когда захочешь снова — «{BTN_RESUME_DATING}».",
        reply_markup=registered_reply_kb(),
    )


@router.message(F.text == BTN_RESUME_DATING)
async def resume_dating(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    redis_cache: RedisCache,
):
    cur = await state.get_state()
    if cur is not None and str(cur).startswith("RegisterForm"):
        await message.answer("Сначала заверши регистрацию.")
        return

    uid = message.from_user.id
    prof = await get_profile(session, uid)
    if not prof:
        await message.answer("Сначала зарегистрируйся: /start")
        return

    if prof.is_active:
        await message.answer("Ты уже в поиске — можно смотреть анкеты.")
        return

    await set_profile_active(session, uid, active=True)
    await session.commit()
    await redis_cache.set_feed(uid, [])
    await message.answer(
        "Снова в поиске! Нажми «Следующая анкета», чтобы посмотреть ленту.",
        reply_markup=registered_reply_kb(),
    )


@router.message(F.text == BTN_NEXT_PROFILE)
async def reply_keyboard_next(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    redis_cache: RedisCache,
):
    cur = await state.get_state()
    if cur is not None and str(cur).startswith("RegisterForm"):
        await message.answer("Сначала заверши регистрацию — ответь на вопрос бота выше.")
        return
    uid = message.from_user.id
    res = await session.execute(select(User).where(User.telegram_id == uid))
    user = res.scalar_one_or_none()
    if not user or not user.is_registered:
        await message.answer("Сначала зарегистрируйся: /start")
        return
    try:
        await show_next_profile(message, session, redis_cache)
    except Exception:
        logger.exception("reply_keyboard_next failed user %s", uid)
        retry_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить поиск анкет",
                        callback_data="refresh_feed",
                    )
                ]
            ]
        )
        await message.answer(
            "Не удалось загрузить ленту. Проверь Redis или нажми кнопку.",
            reply_markup=retry_kb,
        )


@router.message(RegisterForm.name)
async def register_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Сколько тебе лет?")
    await state.set_state(RegisterForm.age)


@router.message(RegisterForm.age)
async def register_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введи число")
        return
    age = int(message.text)
    if age < 14 or age > 120:
        await message.answer("Введи реальный возраст (число).")
        return
    await state.update_data(age=age)
    await message.answer("В каком городе ты живёшь?")
    await state.set_state(RegisterForm.city)


@router.message(RegisterForm.city)
async def register_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await message.answer(
        "Укажи свой пол — нажми кнопку ниже или напиши «мужской» / «женский». "
        "Можно «Пропустить пол», если не хочешь показывать пол.",
        reply_markup=gender_registration_kb(),
    )
    await state.set_state(RegisterForm.gender)


@router.message(RegisterForm.gender)
async def register_gender(message: Message, state: FSMContext):
    parsed = try_parse_registration_gender(message.text or "")
    if parsed is None:
        await message.answer(
            "Не понял. Выбери «Мужской» / «Женский» кнопкой или напиши одно из этих слов.",
            reply_markup=gender_registration_kb(),
        )
        return

    gender_val = None if parsed == "skip" else parsed
    await state.update_data(gender=gender_val)
    await message.answer(
        "Несколько слов о себе (или «-» чтобы пропустить):",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(RegisterForm.bio)


@router.message(RegisterForm.bio)
async def register_bio(message: Message, state: FSMContext):
    await state.update_data(bio=parse_optional_bio(message.text))
    await message.answer("Твои интересы через запятую (или «-» чтобы пропустить):")
    await state.set_state(RegisterForm.interests)


@router.message(RegisterForm.interests)
async def register_interests(message: Message, state: FSMContext):
    await state.update_data(interests=parse_optional_bio(message.text))
    await message.answer(
        f"Минимальный возраст партнёра в поиске ({PARTNER_AGE_MIN}–{PARTNER_AGE_MAX}, например {PARTNER_AGE_MIN}):"
    )
    await state.set_state(RegisterForm.pref_age_from)


@router.message(RegisterForm.pref_age_from)
async def register_pref_from(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer(f"Нужно целое число от {PARTNER_AGE_MIN} до {PARTNER_AGE_MAX}.")
        return
    n = int(message.text)
    if n < PARTNER_AGE_MIN or n > PARTNER_AGE_MAX:
        await message.answer(
            f"Возраст должен быть от {PARTNER_AGE_MIN} до {PARTNER_AGE_MAX}. Введи ещё раз:"
        )
        return
    await state.update_data(pref_age_from=n)
    await message.answer("Максимальный возраст партнёра в поиске (число, не меньше минимального):")
    await state.set_state(RegisterForm.pref_age_to)


@router.message(RegisterForm.pref_age_to)
async def register_pref_to(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Нужно целое число.")
        return
    n = int(message.text)
    if n < PARTNER_AGE_MIN or n > PARTNER_AGE_MAX:
        await message.answer(
            f"Возраст должен быть от {PARTNER_AGE_MIN} до {PARTNER_AGE_MAX}. Введи ещё раз:"
        )
        return
    data = await state.get_data()
    lo = data.get("pref_age_from", PARTNER_AGE_MIN)
    if n < lo:
        await message.answer(
            f"Максимум не может быть меньше минимума ({lo}). Введи число не меньше {lo}:"
        )
        return
    await state.update_data(pref_age_to=n)
    await message.answer(
        "Кого ищешь? Нажми кнопку или напиши: мужчин / женщин / неважно.",
        reply_markup=partner_pref_gender_kb(),
    )
    await state.set_state(RegisterForm.pref_gender)


@router.message(RegisterForm.pref_gender)
async def register_pref_gender(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    redis_cache: RedisCache,
):
    pg = try_parse_partner_pref_gender(message.text or "")
    if pg is None:
        await message.answer(
            "Выбери кнопкой или напиши одно слово: «мужчин», «женщин» или «неважно».",
            reply_markup=partner_pref_gender_kb(),
        )
        return

    await state.update_data(preferred_gender=pg, photo_urls=[])
    await message.answer(
        f"Отправь до {MAX_PHOTOS} фото (сохраним в S3) или напиши «пропустить».\n"
        "После каждого фото можно отправить ещё или написать «готово».",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(RegisterForm.photos)


_SKIP_PHOTO_WORDS = frozenset(
    {"пропустить", "пропуск", "-", "готово", "далее", "skip", "done"}
)


@router.message(RegisterForm.photos, F.photo)
async def register_photo_upload(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    redis_cache: RedisCache,
    bot: Bot,
):
    data = await state.get_data()
    urls: list[str] = list(data.get("photo_urls") or [])
    if len(urls) >= MAX_PHOTOS:
        await message.answer(f"Уже {MAX_PHOTOS} фото. Напиши «готово» для продолжения.")
        return

    url = await upload_telegram_photo(message, bot)
    if not url:
        await message.answer(
            "Не удалось загрузить в S3. Проверь MinIO (`docker compose up -d`) "
            "или напиши «пропустить»."
        )
        return

    urls.append(url)
    await state.update_data(photo_urls=urls)
    left = MAX_PHOTOS - len(urls)
    if left <= 0:
        data = await state.get_data()
        data["photo_urls"] = urls
        await _finalize_registration(message, state, session, redis_cache, data)
    else:
        await message.answer(
            f"Фото {len(urls)}/{MAX_PHOTOS} загружено. Ещё фото или «готово» (осталось {left})."
        )


@router.message(RegisterForm.photos)
async def register_photos_done(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    redis_cache: RedisCache,
):
    text = (message.text or "").strip().lower()
    data = await state.get_data()
    urls: list[str] = list(data.get("photo_urls") or [])

    if text not in _SKIP_PHOTO_WORDS and not urls:
        await message.answer(
            f"Пришли фото или напиши «пропустить». Можно до {MAX_PHOTOS} штук."
        )
        return

    if text in _SKIP_PHOTO_WORDS and not urls:
        data["photo_urls"] = None
    else:
        data["photo_urls"] = urls

    await _finalize_registration(message, state, session, redis_cache, data)


@router.message(Command("next"))
@router.message(F.text == "/next")
async def show_next_profile(
    message: Message,
    session: AsyncSession,
    redis_cache: RedisCache,
    viewer_id: int | None = None,
):
    user_id = viewer_id or message.from_user.id
    FEED_REQUESTS_TOTAL.inc()

    try:
        profile_id = await redis_cache.pop_next(user_id)

        if not profile_id:
            profiles = await get_next_profile(session, user_id)

            if not profiles:
                retry_kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🔄 Обновить поиск анкет",
                                callback_data="refresh_feed",
                            )
                        ]
                    ]
                )
                await message.answer(
                    "Пока других анкет нет — ты один в базе, или под твои фильтры никто не подходит.\n"
                    "Загляни позже или нажми кнопку ниже.",
                    reply_markup=retry_kb,
                )
                return

            profile_ids = [p.user_id for p in profiles]
            profile_id = profile_ids.pop(0)
            await redis_cache.set_feed(user_id, profile_ids)

        profile = await get_profile(session, profile_id)

        if not profile:
            await message.answer("Анкета не найдена, подбираю следующую…")
            return await show_next_profile(message, session, redis_cache, viewer_id=user_id)

        await message.answer(
            format_profile_public(profile),
            reply_markup=get_action_keyboard(profile.user_id),
        )
    except Exception:
        logger.exception("show_next_profile failed for user %s", user_id)
        BOT_ERRORS_TOTAL.labels(handler="show_next_profile").inc()
        await message.answer(
            "Не удалось загрузить ленту. Проверь Redis/PostgreSQL или попробуй /next позже."
        )


@router.callback_query(F.data == "refresh_feed")
async def refresh_feed(callback: CallbackQuery, session: AsyncSession, redis_cache: RedisCache):
    await show_next_profile(callback.message, session, redis_cache, viewer_id=callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data.startswith("like:"))
async def handle_like(callback: CallbackQuery, session: AsyncSession, redis_cache: RedisCache):
    target_id = int(callback.data.split(":")[1])
    actor_id = callback.from_user.id

    await callback.answer()

    await create_interaction(session, actor_id, target_id, "like")
    is_match = await check_match(session, actor_id, target_id)
    await session.commit()

    await publish_interaction_event("like", actor_id, target_id)
    if is_match:
        await publish_interaction_event("match", actor_id, target_id)

    await redis_cache.set_feed(actor_id, [])

    if is_match:
        await send_match_notifications(callback.bot, session, actor_id, target_id)
        return

    await callback.message.answer("Лайк отправлен!")
    await show_next_profile(callback.message, session, redis_cache, viewer_id=actor_id)


@router.callback_query(F.data.startswith("skip:"))
async def handle_skip(callback: CallbackQuery, session: AsyncSession, redis_cache: RedisCache):
    target_id = int(callback.data.split(":")[1])
    actor_id = callback.from_user.id

    await callback.answer()
    await create_interaction(session, actor_id, target_id, "skip")
    await session.commit()
    await publish_interaction_event("skip", actor_id, target_id)
    await callback.message.answer("Пропущено")
    await show_next_profile(callback.message, session, redis_cache, viewer_id=actor_id)


@router.callback_query(F.data.startswith("chat_init:"))
async def handle_chat_init(callback: CallbackQuery, session: AsyncSession):
    partner_id = int(callback.data.split(":")[1])
    uid = callback.from_user.id

    rating = await ensure_rating(session, uid)
    rating.initiated_chats = int(getattr(rating, "initiated_chats", 0) or 0) + 1
    await recalculate_rating_for_user(session, uid)
    await session.commit()
    await publish_interaction_event("chat_init", uid, partner_id)
    await callback.answer("Записано: инициация диалога учтена в рейтинге.", show_alert=False)
    await callback.message.answer(f"✉️ Учтено: ты написал(а) первым(ой) пользователю {partner_id}.")


