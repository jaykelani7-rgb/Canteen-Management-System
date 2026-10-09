"""Ownership checks, verified captures, durable webhook receipts and operator reconciliation."""
import hashlib
import json
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from auth import get_current_admin, get_current_student
from database import get_db
from models import Order, StudentUser, AdminUser
from payment_models import PaymentIntent, PaymentEvent, PaymentRefund
from payment_provider import provider
from order_service import checkout_enabled, lock_student, order_response
from financial_service import (validate_capture, finalize_capture, finalize_refund, topup_response,
    request_refund, process_refund, payment_summary, locked_intent)

payment_router = APIRouter(tags=["Verified Payments"])

class VerifyPayment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    razorpay_order_id: str = Field(pattern=r"^order_[A-Za-z0-9]+$", max_length=100)
    razorpay_payment_id: str = Field(pattern=r"^pay_[A-Za-z0-9]+$", max_length=100)
    razorpay_signature: str = Field(pattern=r"^[a-fA-F0-9]{64}$")

class ReconcilePayment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    providerOrderId: Optional[str] = Field(default=None, pattern=r"^order_[A-Za-z0-9]+$", max_length=100)

class RefundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=255)

def require_payments():
    if not checkout_enabled():
        raise HTTPException(503, "Online payments are not configured")

@payment_router.get("/student/payments/config")
async def payment_config():
    return {"provider": "razorpay" if checkout_enabled() else "disabled", "enabled": checkout_enabled()}

async def find_intent(db, order_id, student_id=None):
    query = select(PaymentIntent).where(PaymentIntent.order_id == order_id)
    if student_id is not None:
        query = query.where(PaymentIntent.student_id == student_id)
    intent = (await db.execute(query)).scalar_one_or_none()
    if intent is None:
        raise HTTPException(404, "Payment intent not found")
    return intent

async def find_topup(db, intent_id, student_id):
    intent = (await db.execute(select(PaymentIntent).where(PaymentIntent.id == intent_id, PaymentIntent.student_id == student_id, PaymentIntent.purpose == "wallet_topup"))).scalar_one_or_none()
    if intent is None:
        raise HTTPException(404, "Wallet top-up not found")
    return intent

async def verify_intent(db, intent, payload):
    require_payments()
    if payload.razorpay_order_id != intent.provider_order_id or not provider.verify_checkout(intent.provider_order_id or "", payload.razorpay_payment_id, payload.razorpay_signature):
        raise HTTPException(400, "Invalid payment signature or order")
    payment = await provider.fetch_payment(payload.razorpay_payment_id)
    if payment.get("id") != payload.razorpay_payment_id:
        raise HTTPException(409, "Gateway payment identifier does not match")
    order = await finalize_capture(db, intent, payment)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Payment has already been assigned") from None
    if intent.state == "refund_required":
        await process_refund(db, intent.id)
    return order

@payment_router.post("/student/orders/{order_id}/payment/verify")
async def verify_payment(order_id:int, payload:VerifyPayment, student:StudentUser=Depends(get_current_student), db:AsyncSession=Depends(get_db)):
    intent = await find_intent(db, order_id, student.id)
    order = await verify_intent(db, intent, payload)
    return await order_response(db, order)

@payment_router.get("/student/wallet/topups")
async def wallet_topups(student:StudentUser=Depends(get_current_student), db:AsyncSession=Depends(get_db)):
    intents = (await db.execute(select(PaymentIntent).where(PaymentIntent.student_id == student.id, PaymentIntent.purpose == "wallet_topup").order_by(PaymentIntent.id.desc()).limit(50))).scalars().all()
    return [await topup_response(db, intent) for intent in intents]

@payment_router.get("/student/wallet/topups/{intent_id}")
async def wallet_topup(intent_id:int, student:StudentUser=Depends(get_current_student), db:AsyncSession=Depends(get_db)):
    return await topup_response(db, await find_topup(db, intent_id, student.id))

@payment_router.post("/student/wallet/topups/{intent_id}/verify")
async def verify_wallet_topup(intent_id:int, payload:VerifyPayment, student:StudentUser=Depends(get_current_student), db:AsyncSession=Depends(get_db)):
    intent = await find_topup(db, intent_id, student.id)
    await verify_intent(db, intent, payload)
    return await topup_response(db, intent)

@payment_router.post("/payments/webhooks/razorpay")
async def razorpay_webhook(request:Request, db:AsyncSession=Depends(get_db)):
    require_payments()
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 1048576:
            raise HTTPException(413, "Webhook payload too large")
        chunks.append(chunk)
    raw = b"".join(chunks)
    event_id = request.headers.get("x-razorpay-event-id", "")
    if not re.fullmatch(r"[A-Za-z0-9_:-]{1,128}", event_id) or not provider.verify_webhook(raw, request.headers.get("x-razorpay-signature", "")):
        raise HTTPException(400, "Invalid webhook authentication")
    body_hash = hashlib.sha256(raw).hexdigest()
    existing = (await db.execute(select(PaymentEvent).where(PaymentEvent.provider == "razorpay", PaymentEvent.event_id == event_id))).scalar_one_or_none()
    if existing:
        if existing.body_hash != body_hash:
            raise HTTPException(409, "Webhook event content changed")
        if existing.payment_intent_id:
            intent = await db.get(PaymentIntent, existing.payment_intent_id)
            if intent.state == "refund_required":
                await process_refund(db, intent.id)
        return {"received": True, "duplicate": True}
    try:
        body = json.loads(raw)
        kind = body["event"]
        payment = body.get("payload", {}).get("payment", {}).get("entity", {})
        remote_refund = body.get("payload", {}).get("refund", {}).get("entity", {})
        if not isinstance(kind, str) or not isinstance(payment, dict) or not isinstance(remote_refund, dict):
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(400, "Malformed webhook") from None
    intent = None
    if kind in {"payment.captured", "payment.authorized", "payment.failed"}:
        intent = (await db.execute(select(PaymentIntent).where(PaymentIntent.provider_order_id == payment.get("order_id")))).scalar_one_or_none() if payment.get("order_id") else None
        if intent is None:
            raise HTTPException(409, "Payment order requires reconciliation")
        if kind == "payment.captured":
            validate_capture(intent, payment)
            verified = await provider.fetch_payment(payment["id"])
            if verified.get("id") != payment["id"]:
                raise HTTPException(409, "Gateway payment identifier does not match")
            await finalize_capture(db, intent, verified)
        else:
            _, _, intent = await locked_intent(db, intent.id)
            if payment.get("amount") != intent.amount_paise or payment.get("currency") != intent.currency:
                raise HTTPException(409, "Payment amount does not match")
            if intent.state not in {"captured", "refund_required", "refunding", "refunded", "refund_review"}:
                intent.state = "authorized" if kind == "payment.authorized" else "failed"
    elif kind in {"refund.created", "refund.processed", "refund.failed", "refund.speed_changed"}:
        payment_id = remote_refund.get("payment_id")
        refund_id = remote_refund.get("id")
        if not re.fullmatch(r"pay_[A-Za-z0-9]+", str(payment_id)) or not re.fullmatch(r"rfnd_[A-Za-z0-9]+", str(refund_id)):
            raise HTTPException(400, "Malformed refund identifiers")
        intent = (await db.execute(select(PaymentIntent).where(PaymentIntent.provider_payment_id == payment_id))).scalar_one_or_none()
        if intent is None:
            raise HTTPException(409, "Refund payment requires reconciliation")
        verified = await provider.fetch_refund(payment_id, refund_id)
        await finalize_refund(db, intent, verified, refund_id)
    db.add(PaymentEvent(provider="razorpay", event_id=event_id, body_hash=body_hash, payment_intent_id=intent.id if intent else None))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        duplicate = (await db.execute(select(PaymentEvent).where(PaymentEvent.provider == "razorpay", PaymentEvent.event_id == event_id))).scalar_one_or_none()
        if not duplicate or duplicate.body_hash != body_hash:
            raise HTTPException(409, "Conflicting payment event") from None
        return {"received": True, "duplicate": True}
    if intent and intent.state == "refund_required":
        await process_refund(db, intent.id)
    return {"received": True}

@payment_router.get("/admin/payments/reconciliation")
async def reconciliation_queue(admin:AdminUser=Depends(get_current_admin), db:AsyncSession=Depends(get_db)):
    intents = (await db.execute(select(PaymentIntent).outerjoin(PaymentRefund, PaymentRefund.payment_intent_id == PaymentIntent.id).where(or_(
        PaymentIntent.state.in_(["creating", "pending", "authorized", "failed", "reconciliation_required", "refund_required", "refund_review"]),
        PaymentRefund.state.in_(["created", "pending", "failed", "reconciliation_required"]), PaymentIntent.unrecovered_refund_paise > 0)).order_by(PaymentIntent.created_at).limit(200))).scalars().all()
    return [await payment_summary(db, intent) for intent in intents]

async def reconcile_intent(db, intent, payload):
    require_payments()
    provider_order_id = intent.provider_order_id or payload.providerOrderId
    if not provider_order_id:
        raise HTTPException(422, "Locate the existing gateway order by receipt; never create another payment order")
    remote = await provider.fetch_order(provider_order_id)
    if remote.get("id") != provider_order_id or remote.get("receipt") != intent.receipt or remote.get("amount") != intent.amount_paise or remote.get("currency") != intent.currency:
        raise HTTPException(409, "Gateway order does not match authoritative intent")
    _, _, intent = await locked_intent(db, intent.id)
    if intent.provider_order_id and intent.provider_order_id != provider_order_id:
        raise HTTPException(409, "A different gateway order is already assigned")
    intent.provider_order_id = provider_order_id
    if intent.state in {"creating", "reconciliation_required"}:
        intent.state = "pending"
    await db.commit()
    payments = await provider.order_payments(provider_order_id)
    captured = [p for p in payments.get("items", []) if p.get("captured") is True and p.get("status") in {"captured", "refunded"}]
    if len(captured) > 1:
        raise HTTPException(409, "Multiple captures require operator review")
    if captured:
        verified = await provider.fetch_payment(captured[0]["id"])
        if verified.get("id") != captured[0]["id"]:
            raise HTTPException(409, "Gateway payment identifier does not match")
        if verified.get("amount_refunded", 0) > 0 or verified.get("status") == "refunded":
            if (verified.get("order_id") != intent.provider_order_id or verified.get("amount") != intent.amount_paise
                    or verified.get("currency") != intent.currency or verified.get("captured") is not True):
                raise HTTPException(409, "Refunded payment does not match authoritative intent")
            _, order, intent = await locked_intent(db, intent.id)
            if intent.provider_payment_id and intent.provider_payment_id != verified["id"]:
                raise HTTPException(409, "A different capture is already assigned")
            intent.provider_payment_id = verified["id"]
            if intent.state not in {"captured", "refunded", "refund_review"}:
                intent.state = "refund_required"
                if order:
                    order.payment_status = "Paid"
                    order.order_status = "Cancelled"
                    order.cancellation_reason = "Payment was refunded before confirmation"
            await db.commit()
            refunds = await provider.payment_refunds(verified["id"])
            items = refunds.get("items", [])
            if len(items) != 1 or not re.fullmatch(r"rfnd_[A-Za-z0-9]+", str(items[0].get("id", ""))):
                student, order, intent = await locked_intent(db, intent.id)
                intent.state = "refund_review"
                if intent.purpose == "wallet_topup":
                    student.is_active = False
                if order:
                    order.order_status = "Cancelled"
                    order.cancellation_reason = "Provider refunds require operator accounting review"
                await db.commit()
                raise HTTPException(409, "Multiple or missing refunds require operator accounting review")
            remote_refund = await provider.fetch_refund(verified["id"], items[0]["id"])
            await finalize_refund(db, intent, remote_refund, items[0]["id"])
        else:
            await finalize_capture(db, intent, verified)
        await db.commit()
    refund = (await db.execute(select(PaymentRefund).where(PaymentRefund.payment_intent_id == intent.id))).scalar_one_or_none()
    if refund and refund.state != "processed":
        await process_refund(db, intent.id)
    return intent

@payment_router.post("/admin/payments/intents/{intent_id}/reconcile")
async def reconcile_any_payment(intent_id:int, payload:ReconcilePayment, admin:AdminUser=Depends(get_current_admin), db:AsyncSession=Depends(get_db)):
    intent = await db.get(PaymentIntent, intent_id)
    if intent is None:
        raise HTTPException(404, "Payment intent not found")
    return await payment_summary(db, await reconcile_intent(db, intent, payload))

@payment_router.post("/admin/payments/{order_id}/reconcile")
async def reconcile_payment(order_id:int, payload:ReconcilePayment, admin:AdminUser=Depends(get_current_admin), db:AsyncSession=Depends(get_db)):
    intent = await reconcile_intent(db, await find_intent(db, order_id), payload)
    return await order_response(db, await db.get(Order, intent.order_id))

@payment_router.post("/admin/payments/intents/{intent_id}/refund")
async def refund_any_payment(intent_id:int, payload:RefundRequest, admin:AdminUser=Depends(get_current_admin), db:AsyncSession=Depends(get_db)):
    require_payments()
    await request_refund(db, intent_id, payload.reason, admin_id=admin.id)
    await process_refund(db, intent_id)
    return await payment_summary(db, await db.get(PaymentIntent, intent_id))

@payment_router.post("/admin/payments/{order_id}/refund")
async def refund_payment(order_id:int, payload:RefundRequest, admin:AdminUser=Depends(get_current_admin), db:AsyncSession=Depends(get_db)):
    require_payments()
    intent = await find_intent(db, order_id)
    await request_refund(db, intent.id, payload.reason, admin_id=admin.id)
    await process_refund(db, intent.id)
    return await order_response(db, await db.get(Order, order_id))
