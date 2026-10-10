"""Authoritative order pricing and serialized wallet/order transitions."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import uuid
from fastapi import HTTPException
from sqlalchemy import select, func, text
from config import settings
from models import FoodItem, StudentUser, Order, WalletTransaction, Notification
from payment_models import PaymentIntent

def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

async def lock_student(db, student_id, require_active=True):
    student = (await db.execute(select(StudentUser).where(StudentUser.id == student_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not student or (require_active and not student.is_active):
        raise HTTPException(403, "Student account is unavailable")
    return student

def checkout_enabled():
    return settings.PAYMENT_PROVIDER == "razorpay" and bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET and settings.RAZORPAY_WEBHOOK_SECRET)

async def order_response(db, order):
    data = order.to_dict()
    intent = (await db.execute(select(PaymentIntent).where(PaymentIntent.order_id == order.id))).scalar_one_or_none()
    deadline = intent.expires_at if intent else None
    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if intent and intent.provider_order_id and order.payment_status == "Pending" and order.order_status != "Cancelled" and (deadline is None or deadline > datetime.now(timezone.utc)):
        data["checkout"] = {"provider": intent.provider, "keyId": settings.RAZORPAY_KEY_ID, "providerOrderId": intent.provider_order_id, "amountPaise": intent.amount_paise, "currency": intent.currency}
    data["refundStatus"] = None
    if intent:
        from payment_models import PaymentRefund
        refund = (await db.execute(select(PaymentRefund).where(PaymentRefund.payment_intent_id == intent.id))).scalar_one_or_none()
        data["refundStatus"] = refund.state if refund else None
    return data

async def create_order(db, student_id, payload, idempotency_key):
    if not 16 <= len(idempotency_key) <= 128 or not all(c.isalnum() or c in "-_:." for c in idempotency_key):
        raise HTTPException(422, "A valid Idempotency-Key is required")
    canonical = {"items": sorted([{"id": i.id, "qty": i.qty, "customizations": sorted(i.customizations)} for i in payload.items], key=lambda i: (i["id"], str(i["customizations"]))), "paymentMethod": payload.paymentMethod, "instructions": payload.specialInstructions or ""}
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    student = await lock_student(db, student_id)
    existing = (await db.execute(select(Order).where(Order.student_id == student_id, Order.idempotency_key == idempotency_key))).scalar_one_or_none()
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(409, "This checkout key was already used for another cart")
        return await order_response(db, existing)
    gateway = payload.paymentMethod != "wallet"
    if gateway and not checkout_enabled():
        raise HTTPException(503, "Online payments are not configured; no payment was taken")
    catalogue = (await db.execute(select(FoodItem).where(FoodItem.id.in_([i.id for i in payload.items])).with_for_update(read=True))).scalars().all()
    by_id = {i.id: i for i in catalogue}
    total = Decimal("0.00")
    formatted = []
    prep = 5
    for request in payload.items:
        item = by_id.get(request.id)
        if not item or not item.is_available or not item.image_id or not item.image_confirmed:
            raise HTTPException(409, "An item is unavailable; refresh the menu")
        from image_service import stored_image, image_url
        try:
            photograph = await stored_image(db, item.image_id)
        except HTTPException as error:
            if error.status_code == 404:
                raise HTTPException(409, "An item photograph is unavailable; refresh the menu") from None
            raise
        if not photograph.rights_confirmed or photograph.published_at is None:
            raise HTTPException(409, "An item photograph is unavailable; refresh the menu")
        from routes import is_time_in_window
        from zoneinfo import ZoneInfo
        if not is_time_in_window(datetime.now(ZoneInfo("Asia/Kolkata")).time(), item.timing_window):
            raise HTTPException(409, "An item is outside its serving window")
        options = {o["name"]: money(o["price"]) for o in item.customizations or []}
        if len(set(request.customizations)) != len(request.customizations) or any(o not in options for o in request.customizations):
            raise HTTPException(422, "Invalid item customization")
        price = money(item.price) + sum((options[o] for o in request.customizations), Decimal("0"))
        total += price * request.qty
        prep = max(prep, item.prep_mins)
        photo = image_url(item.image_id)
        formatted.append({"id": item.id, "name": item.name, "qty": request.qty, "price": float(price), "customizations": request.customizations, "photo": photo, "photoCredits": photo + "/credits"})
    # Current canteen checkout charges only the authoritative item subtotal.
    # Existing orders retain their original recorded fees and tax amounts.
    fee = money(0)
    tax = money(0)
    payable = money(total + fee + tax)
    if payable <= 0 or payable >= Decimal("10000000000"):
        raise HTTPException(422, "Order total is unsupported")
    if gateway and payable * 100 > 2147483647:
        raise HTTPException(422, "Gateway order total is unsupported")
    if not gateway and money(student.wallet_balance) < payable:
        raise HTTPException(400, "Insufficient wallet balance")
    ahead = (await db.execute(select(func.count()).select_from(Order).where(Order.order_status.in_(["Queued", "Preparing", "Delayed"])))).scalar_one()
    order = Order(order_number="T" + uuid.uuid4().hex[:18], student_id=student_id, items_json=formatted, item_total=total, packaging_fee=fee, gst_amount=tax, total_amount=payable, payment_method=payload.paymentMethod, payment_status="Pending" if gateway else "Paid", order_status="Payment Pending" if gateway else "Queued", idempotency_key=idempotency_key, request_fingerprint=fingerprint, queue_position=ahead+1, prep_time_minutes=prep + ahead*2, estimated_ready_at=datetime.now(timezone.utc)+timedelta(minutes=prep+ahead*2), special_instructions=payload.specialInstructions)
    db.add(order)
    await db.flush()
    number = (await db.execute(text("SELECT nextval('canteen_order_number_seq')"))).scalar_one() if db.bind.dialect.name == "postgresql" else 1000 + order.id
    order.order_number = "#" + str(number)
    order.pickup_token = str(number)
    order.qr_code_data = "SCO-ORDER-" + order.order_number
    if gateway:
        intent = PaymentIntent(order_id=order.id, student_id=student_id, provider="razorpay", amount_paise=int(payable * 100), currency="INR", receipt="canteen_"+str(order.id), state="creating", expires_at=datetime.now(timezone.utc)+timedelta(minutes=settings.PAYMENT_ORDER_EXPIRY_MINUTES))
        db.add(intent)
    else:
        student.wallet_balance = money(student.wallet_balance) - payable
        db.add(WalletTransaction(student_id=student_id, amount=payable, transaction_type="debit", payment_method="Wallet", description="Payment for " + order.order_number, order_id=order.id, status="success"))
        record_paid(db, student, order)
    await db.commit()
    await db.refresh(order)
    if gateway:
        from payment_provider import provider
        try:
            result = await provider.create_order(intent.amount_paise, intent.receipt, order.id)
        except Exception:
            intent.state = "reconciliation_required"
            await db.commit()
            raise HTTPException(503, "Payment initialization is pending reconciliation; retry using the same checkout")
        if result.get("amount") != intent.amount_paise or result.get("currency") != "INR" or not result.get("id"):
            intent.state = "reconciliation_required"
            await db.commit()
            raise HTTPException(502, "Payment provider returned inconsistent details")
        intent.provider_order_id = result["id"]
        intent.state = "pending"
        await db.commit()
    return await order_response(db, order)

def record_paid(db, student, order):
    student.total_orders += 1
    student.total_spent = money(student.total_spent) + money(order.total_amount)
    db.add(Notification(student_id=student.id, title="Order " + order.order_number + " confirmed", body="Payment verified. Your order is in the canteen queue.", notification_type="order_update", emoji="✅", color_theme="mint", order_id=order.id))

TRANSITIONS = {"Queued": {"Preparing", "Cancelled"}, "Preparing": {"Ready", "Delayed", "Cancelled"}, "Delayed": {"Preparing", "Ready", "Cancelled"}, "Ready": {"Picked Up", "Completed"}, "Picked Up": {"Completed"}, "Payment Pending": {"Cancelled"}, "Completed": set(), "Cancelled": set()}

async def change_status(db, order_id, target, reason=None, student_id=None, admin_id=None):
    owner = (await db.execute(select(Order.student_id).where(Order.id == order_id))).scalar_one_or_none()
    if owner is None or (student_id is not None and owner != student_id):
        raise HTTPException(404, "Order not found")
    student = await lock_student(db, owner, require_active=False)
    order = (await db.execute(select(Order).where(Order.id == order_id).with_for_update().execution_options(populate_existing=True))).scalar_one()
    if order.order_status == target:
        return await order_response(db, order)
    if target not in TRANSITIONS.get(order.order_status, set()):
        raise HTTPException(409, "This order status transition is not allowed")
    if student_id is not None:
        if target == "Cancelled" and order.order_status not in {"Queued", "Payment Pending"}:
            raise HTTPException(409, "The canteen has already started this order")
        if target != "Cancelled" and target != "Picked Up":
            raise HTTPException(403, "A counter administrator must change this status")
    if target == "Cancelled":
        if not reason or not reason.strip():
            raise HTTPException(422, "A cancellation reason is required")
        if order.payment_status == "Paid" and order.payment_method != "wallet":
            from financial_service import request_refund, process_refund
            intent = (await db.execute(select(PaymentIntent).where(PaymentIntent.order_id == order.id))).scalar_one_or_none()
            if intent is None:
                raise HTTPException(409, "This legacy payment requires operator reconciliation")
            await request_refund(db, intent.id, reason, admin_id=admin_id, student_id=student_id)
            await process_refund(db, intent.id)
            return await order_response(db, order)
        order.cancellation_reason = reason.strip()[:255]
        if order.payment_method == "wallet" and order.payment_status == "Paid":
            student.wallet_balance = money(student.wallet_balance) + money(order.total_amount)
            student.total_spent = max(Decimal("0"), money(student.total_spent) - money(order.total_amount))
            order.payment_status = "Refunded"
            db.add(WalletTransaction(student_id=owner, amount=order.total_amount, transaction_type="credit", payment_method="Refund", description="Refund for " + order.order_number, order_id=order.id, status="success"))
    elif order.payment_status != "Paid":
        raise HTTPException(409, "Only a verified paid order can enter the kitchen")
    order.order_status = target
    if target == "Ready":
        order.ready_at = datetime.now(timezone.utc)
        db.add(Notification(student_id=owner, title="Your food is ready! 🔔", body=order.order_number + " is ready at " + order.pickup_counter, notification_type="order_update", emoji="🔔", color_theme="mint", order_id=order.id))
    if target == "Completed":
        order.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(order)
    return await order_response(db, order)
