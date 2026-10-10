"""One existing PostgreSQL database; migrations never create another database."""
import asyncio
import os
import re
from importlib.util import find_spec
from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine
from config import settings
from migrations.schema_guard import constrain_transactions_to_schema
from database import Base
import models
import recovery_models
if find_spec("payment_models"):
    import payment_models

config = context.config
target_metadata = Base.metadata
url = os.getenv("MIGRATION_DATABASE_URL") or config.get_main_option("sqlalchemy.url") or settings.DATABASE_URL
schema = os.getenv("MIGRATION_SCHEMA")
if schema and not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}", schema):
    raise RuntimeError("Invalid migration schema identifier")

def run_sync(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

async def run_online():
    engine = create_async_engine(url, poolclass=pool.NullPool, connect_args={"statement_cache_size": 0})
    if schema:
        constrain_transactions_to_schema(engine.sync_engine, schema)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_sync)
    finally:
        await engine.dispose()

if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle":"named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
