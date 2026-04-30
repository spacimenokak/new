import aiosqlite
from pathlib import Path

from app import config


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv (
                k TEXT PRIMARY KEY NOT NULL,
                v TEXT NOT NULL
            );
            """
        )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def get(self, key: str) -> str | None:
        assert self._conn
        cur = await self._conn.execute("SELECT v FROM kv WHERE k = ?", (key,))
        row = await cur.fetchone()
        return row["v"] if row else None

    async def upsert(self, key: str, value: str) -> None:
        assert self._conn
        await self._conn.execute(
            "INSERT INTO kv(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
            (key, value),
        )
        await self._conn.commit()

    async def delete_all(self) -> None:
        assert self._conn
        await self._conn.execute("DELETE FROM kv;")
        await self._conn.commit()

    async def seed(self, n: int, seed_tag: str = "seed") -> None:
        assert self._conn
        await self.delete_all()
        await self._conn.executemany(
            "INSERT INTO kv(k, v) VALUES(?, ?)",
            [(str(i), f"{seed_tag}-{i}") for i in range(n)],
        )
        await self._conn.commit()


db = Database(config.DB_PATH)
