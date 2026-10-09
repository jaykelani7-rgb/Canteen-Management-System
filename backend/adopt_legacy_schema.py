"""Default is read-only. --stamp-baseline only adds validated Alembic version metadata."""
import argparse
import asyncio
import os
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine
from migrations.preflight import validate_legacy_schema
from config import settings

async def validate():
    engine = create_async_engine(os.getenv("MIGRATION_DATABASE_URL") or settings.DATABASE_URL,connect_args={"statement_cache_size":0})
    try:
        async with engine.connect() as connection:
            schema = os.getenv("MIGRATION_SCHEMA")
            if schema:
                import re
                from sqlalchemy import text
                if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}",schema): raise RuntimeError("Invalid migration schema")
                await connection.execute(text('SET search_path TO "'+schema+'"'))
            return await connection.run_sync(validate_legacy_schema)
    finally:
        await engine.dispose()

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stamp-baseline",action="store_true")
    args=parser.parse_args()
    tables=asyncio.run(validate())
    print("Legacy schema and financial preflight passed for",len(tables),"tables; no application records changed.")
    if args.stamp_baseline:
        command.stamp(Config(str(Path(__file__).with_name("alembic.ini"))),"0001_legacy_baseline")
        print("Baseline revision metadata saved. Review the backup and run alembic upgrade head separately.")
