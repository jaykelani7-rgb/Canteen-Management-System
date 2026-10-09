import json
from urllib.parse import urlsplit
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
# Database Engine & Session Factory (Supports PostgreSQL & SQLite)
# -------------------------------------------------------------------------
is_sqlite = settings.DATABASE_URL.startswith("sqlite")
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    **({"connect_args": {"check_same_thread": False}} if is_sqlite else {"pool_size": settings.DATABASE_POOL_SIZE, "max_overflow": settings.DATABASE_MAX_OVERFLOW, "connect_args": {"statement_cache_size": 0}}),
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
        redis_url = settings.REDIS_URL
        parsed = urlsplit(redis_url)
        # Docker Desktop publishes IPv4 loopback; Windows may resolve localhost to IPv6 first.
        # Keep production and TLS hostnames intact, including their certificate validation.
        if settings.ENVIRONMENT != "production" and parsed.scheme == "redis" and parsed.hostname == "localhost":
            account = parsed.netloc.rsplit("@", 1)[0] + "@" if "@" in parsed.netloc else ""
            redis_url = parsed._replace(netloc=account + "127.0.0.1:" + str(parsed.port or 6379)).geturl()
        redis_client = aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=False,
            health_check_interval=30,
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
        print(f"[Redis Warning] Cache GET error for key '{key}': {type(e).__name__}")
    return None


async def cache_set(key: str, value: Any, ttl_seconds: int = settings.CACHE_TTL_SECONDS) -> bool:
    """Serialize and cache an object in Redis with time-to-live."""
    try:
        client = get_redis_client()
        serialized = json.dumps(value, default=str)
        await client.set(key, serialized, ex=ttl_seconds)
        return True
    except Exception as e:
        print(f"[Redis Warning] Cache SET error for key '{key}': {type(e).__name__}")
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
        print(f"[Redis Warning] Cache Invalidation error for prefix '{prefix}': {type(e).__name__}")
    return 0


# -------------------------------------------------------------------------
# Database Initialization Utility
# -------------------------------------------------------------------------
async def init_db() -> None:
    """Create all tables in the database if they do not already exist."""
    if getattr(settings, "ENVIRONMENT", "development") == "production":
        raise RuntimeError("Production schema changes must use reviewed Alembic migrations")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
