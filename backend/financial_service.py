"""Serialize student balances and persist refund keys before any provider call."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import re
import uuid
from fastapi import HTTPException
from sqlalchemy import select
from models import Order, WalletTransaction, StudentUser
from payment_models import PaymentIntent, PaymentRefund
from payment_provider import provider
from order_service import lock_student, money, checkout_enabled, record_paid

def utcnow():
    return datetime.now(timezone.utc)

def expired(value):
    return value is not None and (value if value.tzinfo else value.replace(tzinfo=timezone.utc)) <= utcnow()

async def locked_intent(db, intent_id):
    snapshot = await db.get(PaymentIntent, intent_id)
    if snapshot is None:
        raise HTTPException(404, "Payment intent not found")
    student = await lock_student(db, snapshot.student_id, require_active=False)
    order = None
    if snapshot.order_id is not None:
        order = (await db.execute(select(Order).where(Order.id == snapshot.order_id).with_for_update().execution_options(populate_existing=True))).scalar_one()
    intent = (await db.execute(select(PaymentIntent).where(PaymentIntent.id == intent_id).with_for_update().execution_options(populate_existing=True))).scalar_one()
    return student, order, intent

async def refund_record(db, intent):
    return (await db.execute(select(PaymentRefund).where(PaymentRefund.payment_intent_id == intent.id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()

async def ensure_refund(db, intent, reason, admin_id=None, student_id=None):
    existing = await refund_record(db, intent)
    if existing:
        return existing
    refund = PaymentRefund(payment_intent_id=intent.id, amount_paise=intent.amount_paise, currency=intent.currency,
        idempotency_key="refund_" + uuid.uuid4().hex, receipt="refund_" + str(intent.id), reason=reason[:255],
        requested_by_admin_id=admin_id, requested_by_student_id=student_id, state="created")
    db.add(refund)
    await db.flush()
    return refund

def validate_capture(intent, payment):
    if (payment.get("order_id") != intent.provider_order_id or type(payment.get("amount")) is not int
            or payment.get("amount") != intent.amount_paise or payment.get("currency") != intent.currency
            or payment.get("status") != "captured" or payment.get("captured") is not True
            or payment.get("amount_refunded", 0) != 0 or payment.get("refund_status") not in {None, "none"}
            or not re.fullmatch(r"pay_[A-Za-z0-9]+", str(payment.get("id", "")))):
        raise HTTPException(409, "Payment is not a verified capture for this intent and amount")

async def finalize_capture(db, original, payment):
    student, order, intent = await locked_intent(db, original.id)
    validate_capture(intent, payment)
    if intent.provider_payment_id and intent.provider_payment_id != payment["id"]:
        raise HTTPException(409, "Another payment is already linked to this intent")
    if intent.state in {"captured", "refund_required", "refunding", "refunded", "refund_review"}:
        return order
    intent.provider_payment_id = payment["id"]
    if intent.purpose == "wallet_topup":
        if not student.is_active:
            intent.state = "refund_required"
            await ensure_refund(db, intent, "Student account disabled before wallet credit")
        elif intent.wallet_credited_at is None:
            amount = money(Decimal(intent.amount_paise) / 100)
            student.wallet_balance = money(student.wallet_balance) + amount
            intent.wallet_credited_at = utcnow()
            intent.state = "captured"
            db.add(WalletTransaction(student_id=student.id, amount=amount, transaction_type="credit", payment_method="Razorpay",
                description="Verified wallet top-up", payment_intent_id=intent.id, reference_id=payment["id"], status="success"))
        return None
    # Older paid orders retain their existing statistics when captures are replayed.
    if order.payment_status in {"Paid", "Refunded"}:
        intent.state = "refunded" if order.payment_status == "Refunded" else "captured"
        return order
    order.payment_status = "Paid"
    if order.order_status == "Cancelled" or not student.is_active or expired(intent.expires_at):
        order.order_status = "Cancelled"
        order.cancellation_reason = order.cancellation_reason or ("Payment arrived after checkout expired" if student.is_active else "Student account disabled before payment confirmation")
        intent.state = "refund_required"
        await ensure_refund(db, intent, order.cancellation_reason)
    else:
        order.order_status = "Queued"
        intent.state = "captured"
        record_paid(db, student, order)
    return order

async def topup_response(db, intent):
    student = await db.get(StudentUser, intent.student_id, populate_existing=True)
    checkout = None
    if intent.provider_order_id and intent.state in {"pending", "authorized", "failed"}:
        from config import settings
        checkout = {"provider": intent.provider, "keyId": settings.RAZORPAY_KEY_ID, "providerOrderId": intent.provider_order_id,
                    "amountPaise": intent.amount_paise, "currency": intent.currency}
    return {"id": intent.id, "amount": float(Decimal(intent.amount_paise) / 100), "currency": intent.currency,
            "state": intent.state, "checkout": checkout, "createdAt": intent.created_at.isoformat(), "walletBalance": float(student.wallet_balance)}

async def create_topup(db, student_id, amount, key):
    if not checkout_enabled():
        raise HTTPException(503, "Wallet top-ups are not configured; no money was credited")
    if not key or not 16 <= len(key) <= 128 or not re.fullmatch(r"[A-Za-z0-9_:.-]+", key):
        raise HTTPException(422, "A valid Idempotency-Key is required")
    value = Decimal(str(amount))
    if not value.is_finite() or value < 1 or value > 10000 or value != money(value):
        raise HTTPException(422, "Use an amount from 1 to 10000 INR with at most two decimal places")
    paise = int(value * 100)
    fingerprint = hashlib.sha256(str(paise).encode()).hexdigest()
    await lock_student(db, student_id)
    intent = (await db.execute(select(PaymentIntent).where(PaymentIntent.student_id == student_id, PaymentIntent.purpose == "wallet_topup", PaymentIntent.idempotency_key == key))).scalar_one_or_none()
    if intent:
        if intent.request_fingerprint != fingerprint:
            raise HTTPException(409, "This top-up key was used for a different amount")
        return await topup_response(db, intent)
    intent = PaymentIntent(student_id=student_id, purpose="wallet_topup", provider="razorpay", amount_paise=paise,
        currency="INR", receipt="wallet_" + uuid.uuid4().hex, idempotency_key=key, request_fingerprint=fingerprint, state="creating")
    db.add(intent)
    await db.commit()
    try:
        remote = await provider.create_order(paise, intent.receipt, "wallet_" + str(intent.id))
        if (not re.fullmatch(r"order_[A-Za-z0-9]+", str(remote.get("id", ""))) or remote.get("amount") != paise
                or remote.get("currency") != "INR" or remote.get("receipt") != intent.receipt):
            raise HTTPException(502, "Payment provider returned inconsistent details")
    except HTTPException:
        _, _, intent = await locked_intent(db, intent.id)
        intent.state = "reconciliation_required"
        await db.commit()
        raise HTTPException(503, "Top-up initialization requires reconciliation; retain the same top-up key") from None
    _, _, intent = await locked_intent(db, intent.id)
    if intent.provider_order_id and intent.provider_order_id != remote["id"]:
        raise HTTPException(409, "This top-up already has a gateway order")
    intent.provider_order_id = remote["id"]
    if intent.state == "creating":
        intent.state = "pending"
    await db.commit()
    return await topup_response(db, intent)

async def request_refund(db, intent_id, reason, admin_id=None, student_id=None):
    student, order, intent = await locked_intent(db, intent_id)
    if student_id is not None and student_id != student.id:
        raise HTTPException(404, "Payment intent not found")
    if not reason or not reason.strip():
        raise HTTPException(422, "A refund reason is required")
    existing = await refund_record(db, intent)
    if existing:
        await db.commit()
        return existing
    if not intent.provider_payment_id or intent.state not in {"captured", "refund_required"}:
        raise HTTPException(409, "Only a verified capture can be refunded")
    if intent.purpose == "wallet_topup" and intent.wallet_credited_at:
        raise HTTPException(409, "Credited wallet funds require a reviewed account adjustment")
    if order:
        allowed = {"Queued", "Preparing", "Delayed", "Cancelled"} if student_id is None else {"Queued", "Cancelled"}
        if order.order_status not in allowed:
            raise HTTPException(409, "The canteen has already progressed this order beyond cancellation")
        order.order_status = "Cancelled"
        order.cancellation_reason = reason.strip()[:255]
    # Keep captured state until completion so spending statistics can be reversed once.
    refund = await ensure_refund(db, intent, reason.strip(), admin_id, student_id)
    await db.commit()
    return refund

def validate_refund(intent, remote, expected_id=None):
    if (not re.fullmatch(r"rfnd_[A-Za-z0-9]+", str(remote.get("id", "")))
        or (expected_id and remote.get("id") != expected_id) or remote.get("payment_id") != intent.provider_payment_id
        or type(remote.get("amount")) is not int or remote.get("amount") != intent.amount_paise
        or remote.get("currency") != intent.currency or remote.get("status") not in {"pending", "processed", "failed"}):
        raise HTTPException(409, "Refund does not match the full authoritative payment; operator review required")

async def finalize_refund(db, original, remote, expected_id=None):
    student, order, intent = await locked_intent(db, original.id)
    prior = await refund_record(db, intent)
    if prior and prior.state == "processed":
        if remote.get("payment_id") != intent.provider_payment_id or remote.get("currency") != intent.currency:
            raise HTTPException(409, "Refund identity does not match")
        return prior
    if (re.fullmatch(r"rfnd_[A-Za-z0-9]+", str(remote.get("id", "")))
            and (not expected_id or remote.get("id") == expected_id)
            and remote.get("payment_id") == intent.provider_payment_id and remote.get("currency") == intent.currency
            and type(remote.get("amount")) is int and 0 < remote["amount"] < intent.amount_paise
            and remote.get("status") in {"pending", "processed"}):
        # Partial provider-dashboard refunds require operator accounting review.
        # Stop spending/fulfilment while retaining the authoritative existing ledger.
        intent.state = "refund_review"
        if intent.purpose == "wallet_topup":
            student.is_active = False
        if order:
            order.order_status = "Cancelled"
            order.cancellation_reason = "Partial provider refund requires operator review"
        refund = await refund_record(db, intent)
        if refund:
            refund.state = "manual_review"
        return refund
    validate_refund(intent, remote, expected_id)
    refund = await refund_record(db, intent)
    if refund and refund.provider_refund_id and refund.provider_refund_id != remote["id"]:
        raise HTTPException(409, "Another refund is already linked to this payment")
    if refund is None:
        refund = await ensure_refund(db, intent, "Verified refund initiated at payment provider")
    if refund.state == "processed":
        return refund
    refund.provider_refund_id = remote["id"]
    intent.provider_refund_id = remote["id"]
    refund.state = remote["status"]
    if remote["status"] != "processed":
        return refund
    if order:
        if intent.state == "captured":
            student.total_spent = max(Decimal("0"), money(student.total_spent) - money(order.total_amount))
        order.order_status = "Cancelled"
        order.cancellation_reason = order.cancellation_reason or refund.reason
        order.payment_status = "Refunded"
    elif intent.wallet_credited_at:
        # Dashboard-initiated refunds cannot leave refunded funds spendable.
        amount = money(Decimal(intent.amount_paise) / 100)
        recovered = min(money(student.wallet_balance), amount)
        student.wallet_balance = money(student.wallet_balance) - recovered
        intent.unrecovered_refund_paise = int((amount - recovered) * 100)
        if recovered:
            db.add(WalletTransaction(student_id=student.id, amount=recovered, transaction_type="debit", payment_method="Refund",
                description="Recovery of provider-refunded wallet top-up", payment_intent_id=intent.id, reference_id=remote["id"], status="success"))
        if intent.unrecovered_refund_paise:
            student.is_active = False
    intent.state = "refunded"
    refund.processed_at = utcnow()
    return refund

async def process_refund(db, intent_id):
    """Retry only the persisted full-refund body with the same provider idempotency key."""
    _, _, intent = await locked_intent(db, intent_id)
    refund = await refund_record(db, intent)
    if refund is None or refund.state in {"processed", "manual_review"}:
        await db.commit()
        return refund
    payment_id, amount, receipt, key = intent.provider_payment_id, refund.amount_paise, refund.receipt, refund.idempotency_key
    existing_id = refund.provider_refund_id
    # Commit the durable request before networking; do not hold student locks during HTTP.
    await db.commit()
    try:
        if existing_id:
            remote = await provider.fetch_refund(payment_id, existing_id)
        else:
            created = await provider.create_refund(payment_id, amount, receipt, key)
            validate_refund(intent, created)
            # A POST response alone is not enough to label customer money refunded.
            remote = await provider.fetch_refund(payment_id, created["id"])
        refund = await finalize_refund(db, intent, remote, existing_id or created["id"])
        await db.commit()
        return refund
    except HTTPException:
        await db.rollback()
        _, _, intent = await locked_intent(db, intent_id)
        refund = await refund_record(db, intent)
        if refund and refund.state != "processed":
            refund.state = "reconciliation_required"
        await db.commit()
        return refund

async def payment_summary(db, intent):
    refund = (await db.execute(select(PaymentRefund).where(PaymentRefund.payment_intent_id == intent.id))).scalar_one_or_none()
    return {"paymentIntentId": intent.id, "orderId": intent.order_id, "purpose": intent.purpose, "state": intent.state,
        "amountPaise": intent.amount_paise, "currency": intent.currency, "receipt": intent.receipt,
        "providerOrderId": intent.provider_order_id, "providerPaymentId": intent.provider_payment_id,
        "refundId": refund.provider_refund_id if refund else None, "refundStatus": refund.state if refund else None,
        "unrecoveredRefundPaise": intent.unrecovered_refund_paise, "createdAt": intent.created_at.isoformat()}
