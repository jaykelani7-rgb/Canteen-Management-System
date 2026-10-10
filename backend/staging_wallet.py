"""Operator-only synthetic QA credit. No public HTTP route or payment capture."""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from config import settings
from models import WalletTransaction
from order_service import lock_student, money

REFERENCE = "STAGING-QA-WALLET-CREDIT-V1"
AMOUNT = Decimal("300.00")


async def credit_staging_qa_wallet(db, student_id: str, expected_roll: str):
    """Caller must verify the staging database; serialize credit with wallet spends."""
    if settings.PAYMENT_PROVIDER != "disabled" or not expected_roll.startswith("STGQA"):
        raise HTTPException(403, "Only a verified synthetic staging account can receive this credit")
    student = await lock_student(db, student_id)
    if student.roll_number != expected_roll or student.name != "STAGING QA Student":
        raise HTTPException(403, "Synthetic staging account identity does not match")
    entries = (await db.execute(select(WalletTransaction).where(
        WalletTransaction.student_id == student_id,
        WalletTransaction.reference_id == REFERENCE,
    ))).scalars().all()
    if entries:
        if len(entries) != 1 or (entries[0].amount, entries[0].transaction_type, entries[0].status) != (AMOUNT, "credit", "success"):
            raise HTTPException(409, "Staging credit reference requires operator reconciliation")
        return {"credited": False, "reference": REFERENCE, "amount": AMOUNT,
                "wallet_balance": money(student.wallet_balance), "transaction_id": entries[0].id}
    student.wallet_balance = money(student.wallet_balance) + AMOUNT
    entry = WalletTransaction(student_id=student.id, amount=AMOUNT,
        transaction_type="credit", payment_method="STAGING TEST CREDIT",
        description="STAGING ONLY QA wallet credit; no external payment or money received",
        reference_id=REFERENCE, status="success")
    db.add(entry)
    # Credit and ledger entry are committed together. The session owner rolls
    # back on failure, exactly as it does for authoritative order creation.
    await db.commit()
    return {"credited": True, "reference": REFERENCE, "amount": AMOUNT,
            "wallet_balance": money(student.wallet_balance), "transaction_id": entry.id}
