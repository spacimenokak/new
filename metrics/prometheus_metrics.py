"""Счётчики Prometheus для бота и обработчика событий."""

from prometheus_client import Counter

LIKES_TOTAL = Counter("dating_likes_total", "Лайки анкет")
SKIPS_TOTAL = Counter("dating_skips_total", "Пропуски анкет")
MATCHES_TOTAL = Counter("dating_matches_total", "Взаимные мэтчи")
CHAT_INIT_TOTAL = Counter("dating_chat_init_total", "Инициации диалога после мэтча")
FEED_REQUESTS_TOTAL = Counter("dating_feed_requests_total", "Запросы следующей анкеты")
MQ_EVENTS_PUBLISHED = Counter(
    "dating_redis_events_published_total",
    "События, опубликованные в Redis Stream",
    ["event_type"],
)
MQ_EVENTS_CONSUMED = Counter(
    "dating_redis_events_consumed_total",
    "События, обработанные Redis consumer",
    ["event_type"],
)
REFERRALS_APPLIED = Counter("dating_referrals_applied_total", "Успешные рефералы")
S3_UPLOADS_TOTAL = Counter("dating_s3_uploads_total", "Загрузки фото в S3")
BOT_ERRORS_TOTAL = Counter(
    "dating_bot_errors_total",
    "Ошибки в хендлерах",
    ["handler"],
)
