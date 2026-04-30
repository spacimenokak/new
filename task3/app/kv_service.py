"""Three cache strategies over Redis + SQLite."""

from __future__ import annotations

import asyncio

import redis.asyncio as redis

from app import config
from app.config import CacheStrategy
from app.database import db
from app.metrics import metrics, monotonic_ms


def _rkey(suffix: str) -> str:
    return f"{config.KEY_PREFIX}:{suffix}"


class KVService:
    def __init__(self, r: redis.Redis, strategy: CacheStrategy) -> None:
        self._r = r
        self._strategy = strategy
        self._flush_task: asyncio.Task | None = None
        self._stop_flush = asyncio.Event()

    def start_write_back_flusher(self) -> None:
        if self._strategy != CacheStrategy.WRITE_BACK:
            return
        if self._flush_task and not self._flush_task.done():
            return
        self._stop_flush.clear()
        self._flush_task = asyncio.create_task(self._write_back_flush_loop())

    async def stop_write_back_flusher(self) -> None:
        self._stop_flush.set()
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

    def _value_key(self, key: str) -> str:
        return _rkey(f"val:{key}")

    def _dirty_set(self) -> str:
        return _rkey("dirty")

    async def get(self, key: str) -> str | None:
        t0 = monotonic_ms()
        try:
            if self._strategy == CacheStrategy.CACHE_ASIDE:
                return await self._get_cache_aside(key)
            if self._strategy == CacheStrategy.WRITE_THROUGH:
                return await self._get_write_through(key)
            return await self._get_write_back(key)
        finally:
            await metrics.record_latency_ms(monotonic_ms() - t0)

    async def set(self, key: str, value: str) -> None:
        t0 = monotonic_ms()
        try:
            if self._strategy == CacheStrategy.CACHE_ASIDE:
                await self._set_cache_aside(key, value)
            elif self._strategy == CacheStrategy.WRITE_THROUGH:
                await self._set_write_through(key, value)
            else:
                await self._set_write_back(key, value)
        finally:
            await metrics.record_latency_ms(monotonic_ms() - t0)

    # --- Cache-aside: read through cache; write DB only; invalidate cache ---
    async def _get_cache_aside(self, key: str) -> str | None:
        cached = await self._r.get(self._value_key(key))
        if cached is not None:
            await metrics.add_cache_hit()
            return cached.decode() if isinstance(cached, bytes) else str(cached)
        await metrics.add_cache_miss()
        await metrics.add_db_read()
        row = await db.get(key)
        if row is None:
            return None
        await self._r.set(self._value_key(key), row)
        return row

    async def _set_cache_aside(self, key: str, value: str) -> None:
        await metrics.add_db_write()
        await db.upsert(key, value)
        await self._r.delete(self._value_key(key))

    # --- Write-through: read like cache-aside; write DB + cache ---
    async def _get_write_through(self, key: str) -> str | None:
        cached = await self._r.get(self._value_key(key))
        if cached is not None:
            await metrics.add_cache_hit()
            return cached.decode() if isinstance(cached, bytes) else str(cached)
        await metrics.add_cache_miss()
        await metrics.add_db_read()
        row = await db.get(key)
        if row is None:
            return None
        await self._r.set(self._value_key(key), row)
        return row

    async def _set_write_through(self, key: str, value: str) -> None:
        await metrics.add_db_write()
        await db.upsert(key, value)
        await self._r.set(self._value_key(key), value)

    # --- Write-back: read through cache; write cache first; DB later ---
    async def _get_write_back(self, key: str) -> str | None:
        cached = await self._r.get(self._value_key(key))
        if cached is not None:
            await metrics.add_cache_hit()
            return cached.decode() if isinstance(cached, bytes) else str(cached)
        await metrics.add_cache_miss()
        await metrics.add_db_read()
        row = await db.get(key)
        if row is None:
            return None
        await self._r.set(self._value_key(key), row)
        return row

    async def _set_write_back(self, key: str, value: str) -> None:
        await self._r.set(self._value_key(key), value)
        await self._r.sadd(self._dirty_set(), key)

    async def flush_write_back_dirty(self) -> int:
        """Persist dirty keys from Redis to SQLite. Returns number of keys written."""
        dirty = self._dirty_set()
        keys = await self._r.smembers(dirty)
        if not keys:
            return 0
        n = 0
        for raw in keys:
            k = raw.decode() if isinstance(raw, bytes) else str(raw)
            val = await self._r.get(self._value_key(k))
            if val is None:
                await self._r.srem(dirty, k)
                continue
            v = val.decode() if isinstance(val, bytes) else str(val)
            await metrics.add_db_write()
            await db.upsert(k, v)
            await self._r.srem(dirty, k)
            n += 1
        await metrics.add_wb_flushed(n)
        return n

    async def _write_back_flush_loop(self) -> None:
        interval = config.WRITE_BACK_FLUSH_INTERVAL_S
        while not self._stop_flush.is_set():
            try:
                await asyncio.wait_for(self._stop_flush.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass
            await self.flush_write_back_dirty()

    async def clear_redis_namespace(self) -> None:
        """Delete keys with our prefix (SCAN)."""
        cursor = 0
        prefix = f"{config.KEY_PREFIX}:"
        while True:
            cursor, keys = await self._r.scan(cursor=cursor, match=f"{prefix}*", count=500)
            if keys:
                await self._r.delete(*keys)
            if cursor == 0:
                break

    async def admin_reset(self, seed_rows: int) -> dict:
        if self._strategy == CacheStrategy.WRITE_BACK:
            await self.flush_write_back_dirty()
        await self.clear_redis_namespace()
        await db.delete_all()
        await db.seed(seed_rows)
        await metrics.reset()
        return {"ok": True, "seed_rows": seed_rows, "strategy": self._strategy.value}


def build_redis_client() -> redis.Redis:
    return redis.from_url(config.REDIS_URL, decode_responses=False)
