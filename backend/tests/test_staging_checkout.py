"""Zero-extra-charge orders and explicitly scoped synthetic QA wallet funding."""
from decimal import Decimal
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from auth import create_access_token, credential_fingerprint
from config import settings
from models import FoodItem, Order, StudentUser, WalletTransaction
from staging_wallet import AMOUNT, REFERENCE, credit_staging_qa_wallet
from test_mess import mess_client


async def identity(sessions, balance=Decimal("7.75")):
    async with sessions() as db:
        student = await db.get(StudentUser, "linked-student")
        student.name = "STAGING QA Student"
        student.roll_number = "STGQATESTONLY"
        student.wallet_balance = balance
        await db.commit()
        return {"Authorization": "Bearer " + create_access_token({"sub": student.id,
            "role": "student", "credential_version": credential_fingerprint(student.hashed_passcode)})}


async def test_staging_credit_preserves_balance_and_is_idempotent(mess_client, monkeypatch):
    _, sessions, _ = mess_client
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "disabled")
    await identity(sessions)
    async with sessions() as db:
        first = await credit_staging_qa_wallet(db, "linked-student", "STGQATESTONLY")
        assert first["credited"] and first["wallet_balance"] == Decimal("307.75")
    async with sessions() as db:
        again = await credit_staging_qa_wallet(db, "linked-student", "STGQATESTONLY")
        assert not again["credited"] and again["transaction_id"] == first["transaction_id"]
        entries = (await db.execute(select(WalletTransaction).where(WalletTransaction.reference_id == REFERENCE))).scalars().all()
        assert len(entries) == 1 and entries[0].amount == AMOUNT


async def test_staging_credit_rejects_genuine_identity(mess_client, monkeypatch):
    _, sessions, _ = mess_client
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "disabled")
    async with sessions() as db:
        with pytest.raises(HTTPException) as failure:
            await credit_staging_qa_wallet(db, "linked-student", "STGQANOTTHISSTUDENT")
        assert failure.value.status_code == 403
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 0
        assert (await db.get(StudentUser, "linked-student")).wallet_balance == 0


async def test_staging_credit_and_balance_roll_back_on_commit_failure(mess_client, monkeypatch):
    _, sessions, _ = mess_client
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "disabled")
    await identity(sessions)
    async with sessions() as db:
        async def fail():
            await db.flush()
            raise RuntimeError("isolated simulated persistence failure")
        monkeypatch.setattr(db, "commit", fail)
        with pytest.raises(RuntimeError):
            await credit_staging_qa_wallet(db, "linked-student", "STGQATESTONLY")
        await db.rollback()
    async with sessions() as db:
        assert (await db.get(StudentUser, "linked-student")).wallet_balance == Decimal("7.75")
        assert (await db.execute(select(func.count()).select_from(WalletTransaction))).scalar_one() == 0
