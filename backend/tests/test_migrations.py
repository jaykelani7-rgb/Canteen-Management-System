"""Exercise real migrations only inside a disposable schema of the existing PostgreSQL DB."""
import asyncio
import os
from pathlib import Path
import uuid
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect,text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import CreateSchema,DropSchema
from migrations.legacy_schema import Base as LegacyBase
from migrations.preflight import validate_legacy_schema,validate_financial_data

@pytest_asyncio.fixture
async def migration_db(monkeypatch):
    url=os.getenv("MESS_TEST_DATABASE_URL")
    if not url or not url.startswith("postgresql"): pytest.skip("Financial migration verification requires PostgreSQL")
    schema="migration_test_"+uuid.uuid4().hex
    owner=create_async_engine(url)
    async with owner.begin() as connection: await connection.execute(CreateSchema(schema))
    engine=create_async_engine(url,connect_args={"server_settings":{"search_path":schema},"statement_cache_size":0})
    monkeypatch.setenv("MIGRATION_DATABASE_URL",url)
    monkeypatch.setenv("MIGRATION_SCHEMA",schema)
    config=Config(str(Path(__file__).resolve().parents[1]/"alembic.ini"))
    try: yield engine,config
    finally:
        await engine.dispose()
        assert schema.startswith("migration_test_")
        async with owner.begin() as connection: await connection.execute(DropSchema(schema,cascade=True))
        await owner.dispose()

async def test_frozen_baseline_upgrades_money_and_preserves_data(migration_db):
    engine,config=migration_db
    await asyncio.to_thread(command.upgrade,config,"0001_legacy_baseline")
    async with engine.begin() as connection:
        await connection.execute(LegacyBase.metadata.tables["ala_carte"].insert().values(item_name="Preserve me",price=12.50,timing_window="all_day",is_available=True))
        await insert_legacy_order(connection)
    await asyncio.to_thread(command.upgrade,config,"0003_payment_records")
    async with engine.begin() as connection:
        await connection.execute(text("INSERT INTO payment_intents(order_id,student_id,provider,amount_paise,currency,receipt,state) VALUES(1,'migration-student','razorpay',1000,'INR','legacy_receipt','pending')"))
    await asyncio.to_thread(command.upgrade,config,"head")
    async with engine.connect() as connection:
        assert str((await connection.execute(text("SELECT price FROM ala_carte WHERE item_name='Preserve me'"))).scalar_one())=="12.50"
        def schema_checks(sync):
            inspector=inspect(sync)
            assert {"notification_reads","payment_intents","payment_events","payment_refunds","recovery_challenges"}.issubset(inspector.get_table_names())
            order_columns={c["name"]:c for c in inspector.get_columns("orders")}
            assert "idempotency_key" in order_columns and "request_fingerprint" in order_columns
            assert order_columns["total_amount"]["type"].scale==2
            assert any(i["name"]=="uq_wallet_order_success" and i["unique"] for i in inspector.get_indexes("wallet_transactions"))
            assert any(f["referred_table"]=="orders" for f in inspector.get_foreign_keys("notifications"))
            assert any(f["referred_table"]=="payment_intents" for f in inspector.get_foreign_keys("wallet_transactions"))
            assert any(i["name"]=="uq_wallet_payment_success" and i["unique"] for i in inspector.get_indexes("wallet_transactions"))
        await connection.run_sync(schema_checks)
        intent=(await connection.execute(text("SELECT purpose,state,amount_paise,unrecovered_refund_paise FROM payment_intents WHERE receipt='legacy_receipt'"))).one()
        assert tuple(intent)==("order","pending",1000,0)
        assert str((await connection.execute(text("SELECT wallet_balance FROM students WHERE id='migration-student'"))).scalar_one())=="250.00"
        assert (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()==ScriptDirectory.from_config(config).get_current_head()
        assert (await connection.execute(text("SELECT nextval('canteen_order_number_seq')"))).scalar_one()>1042

async def test_existing_legacy_adoption_is_read_only_and_rejects_drift(migration_db):
    engine,_=migration_db
    async with engine.begin() as connection: await connection.run_sync(LegacyBase.metadata.create_all)
    async with engine.connect() as connection:
        assert len(await connection.run_sync(validate_legacy_schema))==13
        assert "alembic_version" not in await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    async with engine.begin() as connection: await connection.execute(text("ALTER TABLE orders ADD COLUMN unknown_column integer"))
    async with engine.connect() as connection:
        with pytest.raises(RuntimeError,match="column drift"): await connection.run_sync(validate_legacy_schema)

async def test_migration_refuses_orphans_without_removing_history(migration_db):
    engine,_=migration_db
    async with engine.begin() as connection:
        await connection.run_sync(LegacyBase.metadata.create_all)
        await connection.execute(LegacyBase.metadata.tables["notifications"].insert().values(title="Keep audit",body="orphan reference",order_id=999999))
    async with engine.connect() as connection:
        with pytest.raises(RuntimeError,match="orphan order"): await connection.run_sync(validate_financial_data)
        assert (await connection.execute(text("SELECT count(*) FROM notifications"))).scalar_one()==1

async def test_migration_refuses_fractional_cent_values(migration_db):
    engine,_=migration_db
    async with engine.begin() as connection:
        await connection.run_sync(LegacyBase.metadata.create_all)
        await connection.execute(LegacyBase.metadata.tables["ala_carte"].insert().values(item_name="Review precision",price=1.005,timing_window="all_day"))
    async with engine.connect() as connection:
        with pytest.raises(RuntimeError,match="fractional-cent"): await connection.run_sync(validate_financial_data)


async def insert_legacy_order(connection):
    await connection.execute(LegacyBase.metadata.tables["students"].insert().values(id="migration-student",roll_number="MIG001",name="Migration fixture",email="migration@example.invalid",hashed_passcode="not-a-login-credential"))
    await connection.execute(LegacyBase.metadata.tables["orders"].insert().values(id=1,order_number="#1042",student_id="migration-student",item_total=10,total_amount=10))

async def test_migration_refuses_duplicate_successful_ledger_without_deleting(migration_db):
    engine,_=migration_db
    async with engine.begin() as connection:
        await connection.run_sync(LegacyBase.metadata.create_all)
        await insert_legacy_order(connection)
        for _ in range(2):
            await connection.execute(LegacyBase.metadata.tables["wallet_transactions"].insert().values(student_id="migration-student",order_id=1,amount=10,transaction_type="credit",payment_method="Refund",description="Preserve duplicated legacy audit"))
    async with engine.connect() as connection:
        with pytest.raises(RuntimeError,match="duplicate successful order-ledger"):
            await connection.run_sync(validate_financial_data)
        assert (await connection.execute(text("SELECT count(*) FROM wallet_transactions"))).scalar_one()==2
