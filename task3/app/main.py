from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import config
from app.config import CacheStrategy
from app.database import db
from app.kv_service import KVService, build_redis_client
from app.metrics import metrics

redis_client: redis.Redis | None = None
kv: KVService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, kv
    strategy = config.get_strategy()
    redis_client = build_redis_client()
    await db.connect()
    kv = KVService(redis_client, strategy)
    if strategy == CacheStrategy.WRITE_BACK:
        kv.start_write_back_flusher()
    yield
    if kv:
        await kv.stop_write_back_flusher()
    await db.close()
    if redis_client:
        await redis_client.aclose()
        redis_client = None
    kv = None


app = FastAPI(title="Cache comparison KV API", lifespan=lifespan)


class ItemBody(BaseModel):
    value: str = Field(..., min_length=1, max_length=4096)


@app.get("/health")
async def health():
    return {"status": "ok", "strategy": config.get_strategy().value}


@app.get("/items/{key}")
async def get_item(key: str):
    if not kv:
        raise HTTPException(503, "not ready")
    v = await kv.get(key)
    if v is None:
        raise HTTPException(404, "not found")
    return {"key": key, "value": v}


@app.put("/items/{key}")
async def put_item(key: str, body: ItemBody):
    if not kv:
        raise HTTPException(503, "not ready")
    await kv.set(key, body.value)
    return {"key": key, "value": body.value}


@app.get("/metrics")
async def get_metrics():
    if not kv:
        raise HTTPException(503, "not ready")
    snap = await metrics.snapshot()
    dirty_count = 0
    if config.get_strategy() == CacheStrategy.WRITE_BACK and redis_client:
        dirty_count = await redis_client.scard(kv._dirty_set())
    snap["write_back_dirty_keys_pending"] = dirty_count
    snap["strategy"] = config.get_strategy().value
    return snap


class ResetBody(BaseModel):
    seed_rows: int = Field(10_000, ge=1, le=500_000)


@app.post("/admin/reset")
async def admin_reset(body: ResetBody):
    if not kv:
        raise HTTPException(503, "not ready")
    return await kv.admin_reset(body.seed_rows)


@app.post("/admin/reset-counters")
async def admin_reset_counters():
    """Clear server metrics only (DB and Redis unchanged). Use after warmup before timed run."""
    await metrics.reset()
    return {"ok": True}


@app.post("/admin/flush")
async def admin_flush():
    """Write-back only: flush dirty keys to DB immediately."""
    if not kv or config.get_strategy() != CacheStrategy.WRITE_BACK:
        raise HTTPException(400, "flush only for write_back strategy")
    n = await kv.flush_write_back_dirty()
    return {"flushed": n}
