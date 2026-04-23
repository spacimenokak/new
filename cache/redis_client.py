import redis.asyncio as redis
import json

class RedisCache:
    def __init__(self):
        self.redis = None
    
    async def connect(self):
        self.redis = await redis.from_url("redis://localhost:6379", decode_responses=True)
    
    async def get_feed(self, user_id: int):
        """Достать очередь анкет для пользователя"""
        key = f"feed:{user_id}"
        data = await self.redis.lrange(key, 0, -1)
        return [int(x) for x in data] if data else None
    
    async def set_feed(self, user_id: int, profile_ids: list):
        """Сохранить очередь анкет"""
        key = f"feed:{user_id}"
        await self.redis.delete(key)
        if profile_ids:
            await self.redis.rpush(key, *profile_ids)
            await self.redis.expire(key, 3600)  # живёт час
    
    async def pop_next(self, user_id: int):
        """Достать следующую анкету"""
        key = f"feed:{user_id}"
        next_id = await self.redis.lpop(key)
        return int(next_id) if next_id else None