"""Pin explicit schemas inside every PostgreSQL transaction, including pooled hosts."""
import re
from sqlalchemy import event


def constrain_transactions_to_schema(engine, schema):
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}", schema):
        raise RuntimeError("Invalid migration schema identifier")
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Explicit migration schemas require PostgreSQL")

    @event.listens_for(engine, "begin")
    def pin_schema(connection):
        # Startup parameters and session SET can be lost by a transaction pooler.
        # SET LOCAL and this assertion run before application DDL/DML each time.
        connection.exec_driver_sql('SET LOCAL search_path TO "' + schema + '"')
        actual = connection.exec_driver_sql("SELECT current_schema(), current_schemas(false)").one()
        if actual[0] != schema or list(actual[1]) != [schema]:
            raise RuntimeError("Refusing database work: the explicit schema is not isolated")
