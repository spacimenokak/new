import json
import re


class RatingService:
    """Три уровня рейтинга по ТЗ (первичный, поведенческий, комбинированный)."""

    _WORD_RE = re.compile(r"\w+", re.UNICODE)

    @classmethod
    def photo_count(cls, profile) -> int:
        raw = getattr(profile, "photo_urls", None)
        if not raw:
            return 0
        raw = str(raw).strip()
        if not raw:
            return 0
        if raw.startswith("["):
            try:
                data = json.loads(raw)
                return len(data) if isinstance(data, list) else 0
            except json.JSONDecodeError:
                pass
        return len([x for x in raw.replace("\n", ",").split(",") if x.strip()])

    @classmethod
    def calculate_primary_score(cls, profile) -> float:
        """
        Уровень 1: анкета, полнота, география, интересы, фото, первичные предпочтения.
        Результат в диапазоне [0, 1].
        """
        if not profile:
            return 0.0

        score = 0.0
        if getattr(profile, "name", None):
            score += 0.12
        if getattr(profile, "age", None):
            score += 0.12
        if getattr(profile, "city", None):
            score += 0.12
        if getattr(profile, "gender", None):
            score += 0.14

        bio = getattr(profile, "bio", None) or ""
        if len(bio.strip()) >= 20:
            score += 0.14
        elif len(bio.strip()) >= 5:
            score += 0.07

        interests = getattr(profile, "interests", None) or ""
        words = cls._WORD_RE.findall(interests)
        if len(words) >= 3:
            score += 0.12
        elif interests.strip():
            score += 0.06

        photos = cls.photo_count(profile)
        score += min(0.12, photos * 0.04)

        pref_g = getattr(profile, "preferred_gender", None)
        if pref_g and str(pref_g).lower() not in ("", "none"):
            score += 0.06

        p_from = getattr(profile, "preferred_age_from", None)
        p_to = getattr(profile, "preferred_age_to", None)
        if p_from is not None and p_to is not None:
            score += 0.06

        return min(1.0, score)

    @classmethod
    def activity_time_score(cls, activity_by_hour_raw: str | None) -> float:
        """
        Активность по времени суток (UTC): чем ровнее распределение по часам, тем выше балл.
        """
        if not activity_by_hour_raw:
            return 0.5
        try:
            data = json.loads(activity_by_hour_raw)
        except json.JSONDecodeError:
            return 0.5
        if not isinstance(data, dict) or not data:
            return 0.5

        counts = [int(v) for v in data.values() if int(v) > 0]
        if not counts:
            return 0.5

        total = sum(counts)
        spread = min(1.0, len(counts) / 8.0)
        peak_share = max(counts) / total
        balance = 1.0 - min(1.0, peak_share)
        return min(1.0, max(0.0, 0.55 * spread + 0.45 * balance))

    @classmethod
    def calculate_behavioral_score(cls, rating) -> float:
        """
        Уровень 2: лайки, соотношение лайк/скип, мэтчи, инициация диалогов, время суток.
        Результат в диапазоне [0, 1].
        """
        if not rating:
            return 0.5

        likes = int(getattr(rating, "total_likes", 0) or 0)
        skips = int(getattr(rating, "total_skips", 0) or 0)
        total = likes + skips

        likes_ratio = (likes / total) if total > 0 else 0.5

        matches = int(getattr(rating, "total_matches", 0) or 0)
        match_rate = min(1.0, matches / max(likes, 1)) if likes else min(1.0, matches)

        initiated = int(getattr(rating, "initiated_chats", 0) or 0)
        if matches > 0:
            chat_ratio = min(1.0, initiated / matches)
        else:
            chat_ratio = 0.5

        activity = min(1.0, total / 20.0)
        time_score = cls.activity_time_score(getattr(rating, "activity_by_hour", None))

        combined = (
            0.26 * likes_ratio
            + 0.22 * match_rate
            + 0.22 * chat_ratio
            + 0.15 * activity
            + 0.15 * time_score
        )
        return min(1.0, max(0.0, combined))

    @staticmethod
    def calculate_combined(primary: float, behavioral: float, referral_bonus: float = 0.0) -> float:
        """Уровень 3: весовая модель + опциональный реферальный бонус."""
        base = primary * 0.4 + behavioral * 0.6
        return min(1.0, max(0.0, base + referral_bonus))
