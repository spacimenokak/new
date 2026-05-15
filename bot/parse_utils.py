"""Нормализация и строгая проверка значений анкеты."""

from typing import Literal

# Диапазон возраста партнёра в поиске (лет)
PARTNER_AGE_MIN = 18
PARTNER_AGE_MAX = 100


def try_parse_registration_gender(text: str) -> Literal["male", "female"] | Literal["skip"] | None:
    """
    Только мужской / женский (или «-» пропустить пол в анкете).
    Некорректный ввод — None (повторить ввод).
    """
    t = (text or "").strip().lower()
    if t in ("-", "—", "пропустить пол", "пропустить", "skip"):
        return "skip"
    if t in (
        "м",
        "муж",
        "мужской",
        "male",
        "парень",
        "мужчина",
        "мужской пол",
    ):
        return "male"
    if t in (
        "ж",
        "жен",
        "женский",
        "female",
        "девушка",
        "женщина",
        "женский пол",
    ):
        return "female"
    return None


def try_parse_partner_pref_gender(text: str) -> Literal["male", "female", "any"] | None:
    """
    Кого ищет пользователь. Неоднозначные ответы («нет», «не знаю») — None.
    """
    t = (text or "").strip().lower()
    if not t:
        return None

    if t in (
        "любой",
        "любых",
        "любые",
        "всех",
        "any",
        "all",
        "неважно",
        "не важно",
        "неважно!",
        "ваш выбор",
        "без разницы",
    ):
        return "any"

    if t in (
        "мужчин",
        "мужской",
        "мужчины",
        "male",
        "парней",
        "мужиков",
        "мужчину",
    ):
        return "male"

    if t in (
        "женщин",
        "женский",
        "женщины",
        "female",
        "девушек",
        "женщину",
    ):
        return "female"

    return None


def parse_optional_bio(text: str) -> str | None:
    t = (text or "").strip()
    if not t or t in ("-", "—"):
        return None
    return t


def format_profile_public(profile) -> str:
    gender_map = {"male": "мужской", "female": "женский", "other": "другой"}
    pref_map = {"male": "мужчины", "female": "женщины", "any": "неважно", "other": "другой"}
    lines = [
        f"👤 {profile.name}, {profile.age}",
        f"📍 {profile.city}",
        f"⚧ Пол: {gender_map.get((profile.gender or '').lower(), profile.gender or 'не указан')}",
        f"📝 О себе: {profile.bio or '—'}",
        f"🎯 Интересы: {profile.interests or '—'}",
        f"🔎 Ищу: {pref_map.get((profile.preferred_gender or 'any').lower(), 'неважно')}, "
        f"возраст {profile.preferred_age_from}–{profile.preferred_age_to}",
    ]
    return "\n".join(lines)


# Совместимость со старыми вызовами edit_profile
def parse_gender(text: str) -> str | None:
    r = try_parse_registration_gender(text)
    if r == "skip":
        return None
    return r


def parse_preferred_gender(text: str) -> str:
    r = try_parse_partner_pref_gender(text)
    return r if r is not None else "any"
