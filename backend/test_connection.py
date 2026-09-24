import asyncio
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from config import settings


async def test_redis():
    print("\n--- Testing Redis (Upstash) Connection ---")
    try:
        r = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            ssl_cert_reqs=None,
        )
        await r.set("canteen:test:ping", "pong_ok", ex=60)
        val = await r.get("canteen:test:ping")
        info = await r.ping()
        print(f"✅ Redis Connection SUCCESSFUL!")
        print(f"   Ping Response: {info}")
        print(f"   Test Key Read: {val}")
        await r.close()
        return True
    except Exception as e:
        print(f"❌ Redis Connection FAILED: {e}")
        return False


async def test_database():
    print("\n--- Testing PostgreSQL (Supabase) Connection ---")
    try:
        engine = create_async_engine(
            settings.DATABASE_URL,
            connect_args={"statement_cache_size": 0},
            pool_pre_ping=True,
        )
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version(), current_database(), current_user;"))
            row = result.fetchone()
            print(f"✅ PostgreSQL Connection SUCCESSFUL!")
            print(f"   Database: {row[1]}")
            print(f"   User: {row[2]}")
            print(f"   Version: {row[0][:50]}...")
        await engine.dispose()
        return True
    except Exception as e:
        print(f"❌ PostgreSQL Connection FAILED: {e}")
        return False


async def main():
    print(f"Using DATABASE_URL: {settings.DATABASE_URL.split('@')[-1]}")
    print(f"Using REDIS_URL: {settings.REDIS_URL.split('@')[-1]}")
    
    redis_ok = await test_redis()
    db_ok = await test_database()
    
    print("\n==========================================")
    if redis_ok and db_ok:
        print("🎉 ALL SYSTEMS OPERATIONAL: Both Database and Redis are connected and working!")
    else:
        print("⚠️ Some services failed. Check logs above.")
    print("==========================================\n")


if __name__ == "__main__":
    asyncio.run(main())
