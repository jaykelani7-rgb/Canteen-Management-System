"""Only disposable UUID schemas are eligible for real PostgreSQL test work."""
import re
from sqlalchemy.ext.asyncio import create_async_engine
from migrations.schema_guard import constrain_transactions_to_schema


def validate_test_schema(schema):
    if not re.fullmatch(r"(?:mess|student|migration)_test_[a-f0-9]{32}", schema):
        raise RuntimeError("Refusing test work outside a disposable UUID schema")


def schema_test_engine(url, schema):
    validate_test_schema(schema)
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    constrain_transactions_to_schema(engine.sync_engine, schema)
    return engine
