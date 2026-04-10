from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User
from sqlalchemy import select

router = Router()

# FSM для регистрации
class RegisterForm(StatesGroup):
    name = State()
    age = State()
    city = State()

@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext):
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
async def register_city(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    telegram_id = message.from_user.id

    # Обновляем пользователя
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one()
    user.name = data["name"]
    user.age = data["age"]
    user.city = message.text
    user.is_registered = True

    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ Регистрация завершена!\n\n"
        f"Имя: {user.name}\n"
        f"Возраст: {user.age}\n"
        f"Город: {user.city}"
    )