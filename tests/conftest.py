"""Tests run on SQLite + in-memory cache by default. CI also runs them against
real PostgreSQL and Redis by setting TEST_DATABASE_URL and TEST_REDIS_URL."""

import os

import httpx
import pytest

from app.cache import MemoryCache, RedisCache
from app.config import Settings
from app.db import Base, Database
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        redis_url=os.environ.get("TEST_REDIS_URL", ""),
        base_url="https://sho.rt",
        create_limit_per_minute=5,
    )


@pytest.fixture
async def client(settings):
    db = Database(settings.database_url)
    await db.create_tables()
    async with db.engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    await db.dispose()

    if settings.redis_url:
        cache = RedisCache(settings.redis_url)
        await cache._redis.flushdb()
    else:
        cache = MemoryCache()

    app = create_app(settings, cache=cache)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.1", 1234))
        async with httpx.AsyncClient(transport=transport, base_url="https://sho.rt") as c:
            yield c
