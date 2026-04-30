import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class Metrics:
    """In-process counters; reset via reset()."""

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    db_reads: int = 0
    db_writes: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    write_back_flushed_keys: int = 0
    _latency_sum_ms: float = 0.0
    _latency_count: int = 0

    async def add_db_read(self, n: int = 1) -> None:
        async with self._lock:
            self.db_reads += n

    async def add_db_write(self, n: int = 1) -> None:
        async with self._lock:
            self.db_writes += n

    async def add_cache_hit(self, n: int = 1) -> None:
        async with self._lock:
            self.cache_hits += n

    async def add_cache_miss(self, n: int = 1) -> None:
        async with self._lock:
            self.cache_misses += n

    async def record_latency_ms(self, ms: float) -> None:
        async with self._lock:
            self._latency_sum_ms += ms
            self._latency_count += 1

    async def add_wb_flushed(self, n: int = 1) -> None:
        async with self._lock:
            self.write_back_flushed_keys += n

    async def snapshot(self) -> dict:
        async with self._lock:
            total_reads = self.cache_hits + self.cache_misses
            hit_rate = (self.cache_hits / total_reads) if total_reads else 0.0
            avg_srv_ms = (
                (self._latency_sum_ms / self._latency_count) if self._latency_count else 0.0
            )
            return {
                "db_reads": self.db_reads,
                "db_writes": self.db_writes,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "cache_hit_rate": round(hit_rate, 6),
                "server_request_count": self._latency_count,
                "server_avg_latency_ms": round(avg_srv_ms, 4),
                "write_back_dirty_keys_flushed_total": self.write_back_flushed_keys,
            }

    async def reset(self) -> None:
        async with self._lock:
            self.db_reads = 0
            self.db_writes = 0
            self.cache_hits = 0
            self.cache_misses = 0
            self.write_back_flushed_keys = 0
            self._latency_sum_ms = 0.0
            self._latency_count = 0


metrics = Metrics()


def monotonic_ms() -> float:
    return time.perf_counter() * 1000.0
