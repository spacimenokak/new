from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from db.models import User, Profile
from db.crud import get_profile, create_interaction, check_match, get_next_profile, create_profile
from cache.redis_client import RedisCache
from rating.rating_service import RatingService
from bot.keyboards import get_action_keyboard

router = Router()

# FSM для регистрации
class RegisterForm(StatesGroup):
    name = State()
    age = State()
    city = State()

@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext, redis_cache: RedisCache):
    telegram_id = message.from_user.id
    username = message.from_user.username

    # Проверяем, есть ли пользователь в БД
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.commit()
        await message.answer("👋 Привет! Давай познакомимся. Как тебя зовут?")
        await state.set_state(RegisterForm.name)
    else:
        if user.is_registered:
            await message.answer(f"С возвращением, {user.name}!")
            await show_next_profile(message, session, redis_cache)
        else:
            await message.answer("Давай завершим регистрацию. Как тебя зовут?")
            await state.set_state(RegisterForm.name)

@router.message(RegisterForm.name)
async def register_name(message: Message, state: FSMContext, session: AsyncSession):
    await state.update_data(name=message.text)
    await message.answer("Сколько тебе лет?")
    await state.set_state(RegisterForm.age)

@router.message(RegisterForm.age)
async def register_age(message: Message, state: FSMContext, session: AsyncSession):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введи число")
        return
    await state.update_data(age=int(message.text))
    await message.answer("В каком городе ты живешь?")
    await state.set_state(RegisterForm.city)

@router.message(RegisterForm.city)
async def register_city(message: Message, state: FSMContext, session: AsyncSession, redis_cache: RedisCache):
    data = await state.get_data()
    telegram_id = message.from_user.id

    # 1. Обновляем юзера (как и было)
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one()
    user.name = data["name"]
    user.age = data["age"]
    user.city = message.text
    user.is_registered = True

    # 2. ВАЖНО: Создаем профиль в таблице profiles, чтобы анкету видели другие
    await create_profile(
        session, 
        user_id=telegram_id, 
        name=user.name, 
        age=user.age, 
        city=user.city
    )
    await session.commit()
    await state.clear()

    await message.answer(f"✅ Регистрация завершена!\n\nИмя: {user.name}\nВозраст: {user.age}\nГород: {user.city}")
    
    # 3. Сразу показываем первую анкету, чтобы юзер не ждал
    await show_next_profile(message, session, redis_cache)

@router.message(Command("next"))
@router.message(F.text == "/next")
async def show_next_profile(
    message: Message,
    session: AsyncSession,
    redis_cache: RedisCache,
    viewer_id: int | None = None,
):
    # Важно: для callback.message.from_user это будет BOT, поэтому viewer_id
    # нужно передавать явно из callback.from_user.id.
    user_id = viewer_id or message.from_user.id
    
    # Пытаемся достать следующий ID из кэша
    profile_id = await redis_cache.pop_next(user_id)
    
    if not profile_id:
        profiles = await get_next_profile(session, user_id)
        
        if not profiles:
            retry_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать еще раз", callback_data="refresh_feed")]
            ])
            await message.answer("Пока что анкет нет! Загляни чуть позже или нажми кнопку.", reply_markup=retry_kb)
            return
            
        profile_ids = [p.user_id for p in profiles]
        profile_id = profile_ids.pop(0)
        await redis_cache.set_feed(user_id, profile_ids)

    profile = await get_profile(session, profile_id)
    
    if not profile:
        return await show_next_profile(message, session, redis_cache)

    # ВОТ ЭТОГО КУСКА У ТЕБЯ СЕЙЧАС НЕТ! БЕЗ НЕГО БОТ НИЧЕГО НЕ НАПИШЕТ:
    text = f"👤 {profile.name}, {profile.age}\n📍 {profile.city}\n\n{profile.bio or 'О себе пока пусто...'}"
    await message.answer(text, reply_markup=get_action_keyboard(profile.user_id))

@router.callback_query(F.data == "refresh_feed")
async def refresh_feed(callback: CallbackQuery, session: AsyncSession, redis_cache: RedisCache):
    await show_next_profile(callback.message, session, redis_cache, viewer_id=callback.from_user.id)
    await callback.answer()
    
@router.callback_query(F.data.startswith("like:"))
async def handle_like(callback: CallbackQuery, session: AsyncSession, redis_cache: RedisCache):
    target_id = int(callback.data.split(":")[1])
    actor_id = callback.from_user.id
    
    # 1. Сразу отвечаем на кнопку, чтобы убрать "часики"
    await callback.answer()
    
    # 2. Сохраняем лайк
    await create_interaction(session, actor_id, target_id, "like")
    
    # 3. Проверяем взаимность
    is_match = await check_match(session, actor_id, target_id)
    await session.commit()
    
    # 4. Чистим кэш пользователя в Redis, чтобы он не подсунул старый ID
    await redis_cache.set_feed(actor_id, [])
    
    if is_match:
        # Если мэтч — показываем удобную ссылку на профиль в Telegram
        await callback.message.answer(
            "🎉 У вас мэтч!\n"
            f"Открыть профиль: tg://user?id={target_id}"
        )
        return 

    # Если не мэтч — показываем следующую анкету
    await callback.message.answer("Лайк отправлен!")
    await show_next_profile(callback.message, session, redis_cache, viewer_id=actor_id)

@router.callback_query(F.data.startswith("skip:"))
async def handle_skip(callback: CallbackQuery, session: AsyncSession, redis_cache: RedisCache):
    target_id = int(callback.data.split(":")[1])
    actor_id = callback.from_user.id
    
    await callback.answer()
    await create_interaction(session, actor_id, target_id, "skip")
    await session.commit()
    await callback.message.answer("Пропущено")
    await show_next_profile(callback.message, session, redis_cache, viewer_id=actor_id)

@router.callback_query(F.data == "sleep")
async def handle_sleep(callback: CallbackQuery, session: AsyncSession, redis_cache: RedisCache):
    user_id = callback.from_user.id
    profile = await get_profile(session, user_id)
    if profile:
        profile.is_active = not bool(profile.is_active)
        await session.commit()
    await callback.message.answer("💤 Спящий режим включён/выключен")
    await callback.answer()