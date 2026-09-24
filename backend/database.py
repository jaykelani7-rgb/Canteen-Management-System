import json
from typing import Any, AsyncGenerator, Optional
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from config import settings

# -------------------------------------------------------------------------
# PostgreSQL Async Engine & Session Factory
# -------------------------------------------------------------------------
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
    connect_args={"statement_cache_size": 0},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an asynchronous database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# -------------------------------------------------------------------------
# Redis Async Client & Connection Pool
# -------------------------------------------------------------------------
redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """Returns the global async Redis client instance."""
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    return redis_client


async def get_redis() -> aioredis.Redis:
    """FastAPI Dependency for injecting Redis client into route handlers."""
    return get_redis_client()


async def cache_get(key: str) -> Optional[Any]:
    """Retrieve and deserialize a JSON-cached object from Redis."""
    try:
        client = get_redis_client()
        raw_val = await client.get(key)
        if raw_val:
            return json.loads(raw_val)
    except Exception as e:
        # Graceful degradation if Redis is temporarily unreachable
        print(f"[Redis Warning] Cache GET error for key '{key}': {e}")
    return None


async def cache_set(key: str, value: Any, ttl_seconds: int = settings.CACHE_TTL_SECONDS) -> bool:
    """Serialize and cache an object in Redis with time-to-live."""
    try:
        client = get_redis_client()
        serialized = json.dumps(value, default=str)
        await client.set(key, serialized, ex=ttl_seconds)
        return True
    except Exception as e:
        print(f"[Redis Warning] Cache SET error for key '{key}': {e}")
        return False


async def cache_invalidate_prefix(prefix: str) -> int:
    """Invalidate all Redis keys matching a given prefix (e.g. 'canteen:menu:*')."""
    try:
        client = get_redis_client()
        keys = []
        async for key in client.scan_iter(match=f"{prefix}*"):
            keys.append(key)
        if keys:
            await client.delete(*keys)
            return len(keys)
    except Exception as e:
        print(f"[Redis Warning] Cache Invalidation error for prefix '{prefix}': {e}")
    return 0


# -------------------------------------------------------------------------
# Database Initialization Utility
# -------------------------------------------------------------------------
async def init_db() -> None:
    """Create all tables in the database if they do not already exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
