import os
from enum import Enum


class CacheStrategy(str, Enum):
    CACHE_ASIDE = "cache_aside"
    WRITE_THROUGH = "write_through"
    WRITE_BACK = "write_back"


def get_strategy() -> CacheStrategy:
    raw = os.getenv("CACHE_STRATEGY", "cache_aside").strip().lower()
    try:
        return CacheStrategy(raw)
    except ValueError:
        return CacheStrategy.CACHE_ASIDE


REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
DB_PATH = os.getenv("DB_PATH", "./data/kv.db")
KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "task3")
# Write-back: flush interval (seconds) and max dirty keys before forced flush
WRITE_BACK_FLUSH_INTERVAL_S = float(os.getenv("WRITE_BACK_FLUSH_INTERVAL_S", "1.0"))
WRITE_BACK_FLUSH_BATCH = int(os.getenv("WRITE_BACK_FLUSH_BATCH", "500"))
