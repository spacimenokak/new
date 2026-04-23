from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from .models import User, Profile, Rating, Interaction, Match
from datetime import datetime

# ========== Профили ==========

async def get_profile(session: AsyncSession, user_id: int):
    """Получить профиль пользователя по telegram_id"""
    result = await session.execute(
        select(Profile).where(Profile.user_id == user_id)
    )
    return result.scalar_one_or_none()

async def create_profile(session: AsyncSession, user_id: int, name: str, age: int, city: str):
    """Создать профиль после регистрации"""
    profile = Profile(
        user_id=user_id,
        name=name,
        age=age,
        city=city,
        is_filled=True,
        is_active=True
    )
    session.add(profile)
    await session.commit()
    return profile

async def update_profile(session: AsyncSession, user_id: int, **kwargs):
    """Обновить профиль"""
    profile = await get_profile(session, user_id)
    if profile:
        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        await session.commit()
    return profile

# ========== Взаимодействия (лайки/скипы) ==========

async def create_interaction(session: AsyncSession, actor_id: int, target_id: int, type_: str):
    """Создать запись о лайке или скипе"""
    interaction = Interaction(
        actor_id=actor_id,
        target_id=target_id,
        type=type_
    )
    session.add(interaction)
    
    # Обновляем рейтинг (увеличиваем счётчики)
    result = await session.execute(
        select(Rating).where(Rating.user_id == target_id)
    )
    rating = result.scalar_one_or_none()
    
    if rating:
        if type_ == "like":
            rating.total_likes += 1
        else:
            rating.total_skips += 1
    else:
        rating = Rating(
            user_id=target_id,
            total_likes=1 if type_ == "like" else 0,
            total_skips=1 if type_ == "skip" else 0
        )
        session.add(rating)
    
    await session.commit()
    return interaction

async def check_match(session: AsyncSession, user1_id: int, user2_id: int):
    """Проверить, есть ли взаимный лайк и создать мэтч"""
    # Проверяем, лайкнул ли user2 user1
    result = await session.execute(
        select(Interaction).where(
            and_(
                Interaction.actor_id == user2_id,
                Interaction.target_id == user1_id,
                Interaction.type == "like"
            )
        )
    )
    mutual_like = result.scalar_one_or_none()
    
    if mutual_like:
        # Проверяем, нет ли уже мэтча
        result = await session.execute(
            select(Match).where(
                or_(
                    and_(Match.user1_id == user1_id, Match.user2_id == user2_id),
                    and_(Match.user1_id == user2_id, Match.user2_id == user1_id)
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            match = Match(user1_id=user1_id, user2_id=user2_id)
            session.add(match)
            
            # Обновляем счётчик мэтчей в рейтингах
            for uid in [user1_id, user2_id]:
                result = await session.execute(
                    select(Rating).where(Rating.user_id == uid)
                )
                rating = result.scalar_one_or_none()
                if rating:
                    rating.total_matches += 1
            
            await session.commit()
            return True
    return False

# ========== Выдача анкет ==========

async def get_next_profile(session: AsyncSession, current_user_id: int, limit: int = 10):
    """Получить список анкет для показа (с учётом предпочтений)"""
    # Сначала получим профиль текущего пользователя
    current_profile = await get_profile(session, current_user_id)
    if not current_profile:
        return []
    
    # Запрос: другие пользователи, которые активны, не текущий, и которых ещё не лайкнули/скипнули
    result = await session.execute(
        select(Profile)
        .where(Profile.user_id != current_user_id)
        .where(Profile.is_active == True)
        .where(Profile.is_filled == True)
        .where(
            ~select(Interaction).where(
                and_(
                    Interaction.actor_id == current_user_id,
                    Interaction.target_id == Profile.user_id
                )
            ).exists()
        )
        .limit(limit)
    )
    return result.scalars().all()

# ========== Статистика для админа ==========

async def get_user_stats(session: AsyncSession):
    """Получить общую статистику"""
    # Всего пользователей
    total_users = await session.scalar(select(func.count()).select_from(User))
    
    # Всего мэтчей
    total_matches = await session.scalar(select(func.count()).select_from(Match))
    
    # Активных сегодня (условно: зарегистрированных за последние 24 часа)
    yesterday = datetime.utcnow()
    active_today = await session.scalar(
        select(func.count()).select_from(User)
        .where(User.created_at >= yesterday)
    )
    
    return {
        "total_users": total_users or 0,
        "total_matches": total_matches or 0,
        "active_today": active_today or 0
    }

async def ban_user(session: AsyncSession, user_id: int):
    """Заблокировать пользователя (деактивировать профиль)"""
    profile = await get_profile(session, user_id)
    if profile:
        profile.is_active = False
        await session.commit()
        return True
    return False