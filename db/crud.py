import json
import secrets

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, exists, delete
from .models import User, Profile, Rating, Interaction, Match, Referral
from datetime import datetime, timedelta
from rating.rating_service import RatingService

REFERRAL_BONUS_STEP = 0.05
REFERRAL_BONUS_CAP = 0.3


async def ensure_rating(session: AsyncSession, user_id: int) -> Rating:
    result = await session.execute(select(Rating).where(Rating.user_id == user_id))
    rating = result.scalar_one_or_none()
    if rating is None:
        rating = Rating(user_id=user_id)
        session.add(rating)
        await session.flush()
    return rating


async def record_activity_hour(session: AsyncSession, user_id: int, hour_utc: int) -> None:
    """Учёт активности по часу суток (UTC) для поведенческого рейтинга."""
    hour_utc = int(hour_utc) % 24
    rating = await ensure_rating(session, user_id)
    raw = getattr(rating, "activity_by_hour", None) or "{}"
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    key = str(hour_utc)
    data[key] = int(data.get(key, 0)) + 1
    rating.activity_by_hour = json.dumps(data, ensure_ascii=False)


async def ensure_user_referral_code(session: AsyncSession, user: User) -> str:
    if user.referral_code:
        return user.referral_code
    for _ in range(8):
        code = secrets.token_urlsafe(6)[:10].upper().replace("-", "X")
        exists_q = await session.execute(
            select(User.id).where(User.referral_code == code)
        )
        if exists_q.scalar_one_or_none() is None:
            user.referral_code = code
            await session.flush()
            return code
    code = secrets.token_hex(5).upper()
    user.referral_code = code
    await session.flush()
    return code


async def get_user_by_referral_code(session: AsyncSession, code: str) -> User | None:
    if not code:
        return None
    r = await session.execute(
        select(User).where(User.referral_code == code.strip().upper())
    )
    return r.scalar_one_or_none()


async def sync_referral_bonus(session: AsyncSession, inviter_id: int) -> None:
    cnt = await session.scalar(
        select(func.count()).select_from(Referral).where(Referral.inviter_id == inviter_id)
    )
    rating = await ensure_rating(session, inviter_id)
    rating.referral_bonus = min(REFERRAL_BONUS_CAP, int(cnt or 0) * REFERRAL_BONUS_STEP)


async def apply_referral_on_register(
    session: AsyncSession,
    invited_id: int,
    referral_code: str,
) -> bool:
    """Привязка приглашённого к инвайтеру и начисление бонуса (один раз на invited)."""
    code = (referral_code or "").strip().upper()
    if not code:
        return False

    invited = await session.execute(select(User).where(User.telegram_id == invited_id))
    invited_user = invited.scalar_one_or_none()
    if not invited_user or invited_user.invited_by_id:
        return False

    inviter = await get_user_by_referral_code(session, code)
    if not inviter or inviter.telegram_id == invited_id:
        return False

    existing_ref = await session.execute(
        select(Referral).where(Referral.invited_id == invited_id)
    )
    if existing_ref.scalar_one_or_none():
        return False

    invited_user.invited_by_id = inviter.telegram_id
    session.add(
        Referral(
            inviter_id=inviter.telegram_id,
            invited_id=invited_id,
            bonus_amount=REFERRAL_BONUS_STEP,
        )
    )
    await sync_referral_bonus(session, inviter.telegram_id)
    await recalculate_rating_for_user(session, inviter.telegram_id)
    return True


async def recalculate_rating_for_user(session: AsyncSession, user_id: int) -> None:
    profile = await get_profile(session, user_id)
    rating = await ensure_rating(session, user_id)
    if not profile:
        return
    primary = RatingService.calculate_primary_score(profile)
    behavioral = RatingService.calculate_behavioral_score(rating)
    ref = float(getattr(rating, "referral_bonus", 0.0) or 0.0)
    combined = RatingService.calculate_combined(primary, behavioral, ref)
    rating.primary_score = primary
    rating.behavioral_score = behavioral
    rating.combined_score = combined


# ========== Профили ==========

async def get_profile(session: AsyncSession, user_id: int):
    result = await session.execute(select(Profile).where(Profile.user_id == user_id))
    return result.scalar_one_or_none()


async def list_profile_user_ids(session: AsyncSession) -> list[int]:
    """Все user_id с анкетой — для фонового пересчёта рейтингов (Celery)."""
    r = await session.execute(select(Profile.user_id))
    return list(r.scalars().all())


async def create_profile(
    session: AsyncSession,
    user_id: int,
    name: str,
    age: int,
    city: str,
    *,
    gender: str | None = None,
    bio: str | None = None,
    interests: str | None = None,
    preferred_gender: str | None = "any",
    preferred_age_from: int | None = 18,
    preferred_age_to: int | None = 100,
    photo_urls: str | None = None,
):
    """Создать или обновить профиль (идемпотентно по user_id)."""
    existing = await get_profile(session, user_id)
    if existing:
        existing.name = name
        existing.age = age
        existing.city = city
        if gender is not None:
            existing.gender = gender
        if bio is not None:
            existing.bio = bio
        if interests is not None:
            existing.interests = interests
        if preferred_gender is not None:
            existing.preferred_gender = preferred_gender
        if preferred_age_from is not None:
            existing.preferred_age_from = preferred_age_from
        if preferred_age_to is not None:
            existing.preferred_age_to = preferred_age_to
        if photo_urls is not None:
            existing.photo_urls = photo_urls
        existing.is_filled = True
        existing.is_active = True
        await recalculate_rating_for_user(session, user_id)
        return existing

    profile = Profile(
        user_id=user_id,
        name=name,
        age=age,
        city=city,
        gender=gender,
        bio=bio,
        interests=interests,
        preferred_gender=preferred_gender or "any",
        preferred_age_from=preferred_age_from if preferred_age_from is not None else 18,
        preferred_age_to=preferred_age_to if preferred_age_to is not None else 100,
        photo_urls=photo_urls,
        is_filled=True,
        is_active=True,
    )
    session.add(profile)
    await session.flush()
    await recalculate_rating_for_user(session, user_id)
    return profile


async def update_profile(session: AsyncSession, user_id: int, **kwargs):
    profile = await get_profile(session, user_id)
    if not profile:
        return None
    for key, value in kwargs.items():
        if hasattr(profile, key) and value is not None:
            setattr(profile, key, value)
    await recalculate_rating_for_user(session, user_id)
    return profile


async def delete_profile(session: AsyncSession, user_id: int) -> bool:
    """Удалить анкету и рейтинг; пользователь в таблице users остаётся.

    Важно: сбрасываем interactions и matches с этим telegram_id — иначе после
    повторной регистрации старые лайки/скипы навсегда режут ленту (id тот же).
    """
    profile = await get_profile(session, user_id)
    if not profile:
        return False

    await session.execute(
        delete(Interaction).where(
            or_(Interaction.actor_id == user_id, Interaction.target_id == user_id)
        )
    )
    await session.execute(
        delete(Match).where(or_(Match.user1_id == user_id, Match.user2_id == user_id))
    )

    r = await session.execute(select(Rating).where(Rating.user_id == user_id))
    rating = r.scalar_one_or_none()
    if rating:
        await session.delete(rating)

    await session.delete(profile)

    result = await session.execute(select(User).where(User.telegram_id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.is_registered = False
        user.name = None
        user.age = None
        user.city = None

    return True


async def interaction_exists(session: AsyncSession, actor_id: int, target_id: int) -> bool:
    q = await session.execute(
        select(
            exists().where(
                and_(Interaction.actor_id == actor_id, Interaction.target_id == target_id)
            )
        )
    )
    return bool(q.scalar())


# ========== Взаимодействия (лайки/скипы) ==========

async def create_interaction(session: AsyncSession, actor_id: int, target_id: int, type_: str):
    """Одна запись на пару (actor, target). Повторный лайк/скип не меняет счётчики."""
    if await interaction_exists(session, actor_id, target_id):
        result = await session.execute(
            select(Interaction).where(
                and_(Interaction.actor_id == actor_id, Interaction.target_id == target_id)
            )
        )
        return result.scalar_one()

    interaction = Interaction(actor_id=actor_id, target_id=target_id, type=type_)
    session.add(interaction)

    rating = await ensure_rating(session, target_id)
    if type_ == "like":
        rating.total_likes += 1
    else:
        rating.total_skips += 1

    await recalculate_rating_for_user(session, target_id)
    return interaction


async def check_match(session: AsyncSession, user1_id: int, user2_id: int):
    result = await session.execute(
        select(Interaction).where(
            and_(
                Interaction.actor_id == user2_id,
                Interaction.target_id == user1_id,
                Interaction.type == "like",
            )
        )
    )
    mutual_like = result.scalar_one_or_none()

    if not mutual_like:
        return False

    result = await session.execute(
        select(Match).where(
            or_(
                and_(Match.user1_id == user1_id, Match.user2_id == user2_id),
                and_(Match.user1_id == user2_id, Match.user2_id == user1_id),
            )
        )
    )
    if result.scalar_one_or_none():
        return False

    session.add(Match(user1_id=user1_id, user2_id=user2_id))

    for uid in (user1_id, user2_id):
        rating = await ensure_rating(session, uid)
        rating.total_matches += 1
        await recalculate_rating_for_user(session, uid)

    return True


def _viewer_filters(viewer: Profile | None):
    """Фильтры выдачи: предпочтения просматривающего (пол и возраст кандидата)."""
    clauses = []
    if not viewer:
        return clauses

    pg = (viewer.preferred_gender or "any").strip().lower()
    if pg not in ("any", "all", "любой", "любых", "любые"):
        mapping = {
            "male": "male",
            "female": "female",
            "мужской": "male",
            "мужчины": "male",
            "мужчин": "male",
            "женский": "female",
            "женщины": "female",
            "женщин": "female",
            "другой": "other",
            "other": "other",
        }
        want = mapping.get(pg, pg)
        # Анкеты без поля «пол» (пропуск при регистрации) показываем и в узком поиске
        clauses.append(or_(Profile.gender == want, Profile.gender.is_(None)))

    pa_from = viewer.preferred_age_from
    pa_to = viewer.preferred_age_to
    if pa_from is not None and pa_to is not None and pa_from > pa_to:
        pa_from, pa_to = pa_to, pa_from
    if pa_from is not None:
        clauses.append(Profile.age >= pa_from)
    if pa_to is not None:
        clauses.append(Profile.age <= pa_to)

    return clauses


async def get_next_profile(session: AsyncSession, current_user_id: int, limit: int = 10):
    await session.flush()

    viewer = await get_profile(session, current_user_id)

    q = (
        select(Profile)
        .join(Rating, Rating.user_id == Profile.user_id, isouter=True)
        .where(Profile.user_id != current_user_id)
        .where(Profile.is_active == True)
        .where(Profile.is_filled == True)
        .where(
            ~Profile.user_id.in_(
                select(Interaction.target_id).where(Interaction.actor_id == current_user_id)
            )
        )
    )
    for clause in _viewer_filters(viewer):
        q = q.where(clause)

    q = q.order_by(Rating.combined_score.desc().nulls_last()).limit(limit)

    result = await session.execute(q)
    return result.scalars().all()


async def get_user_stats(session: AsyncSession):
    total_users = await session.scalar(select(func.count()).select_from(User))
    total_matches = await session.scalar(select(func.count()).select_from(Match))
    yesterday = datetime.utcnow() - timedelta(days=1)
    active_today = await session.scalar(
        select(func.count()).select_from(User).where(User.created_at >= yesterday)
    )

    return {
        "total_users": total_users or 0,
        "total_matches": total_matches or 0,
        "active_today": active_today or 0,
    }


async def set_profile_active(session: AsyncSession, user_id: int, *, active: bool) -> bool:
    """Скрыть/вернуть анкету в ленту (мэтчи и история не трогаются)."""
    profile = await get_profile(session, user_id)
    if not profile:
        return False
    profile.is_active = active
    return True


async def ban_user(session: AsyncSession, user_id: int):
    return await set_profile_active(session, user_id, active=False)
