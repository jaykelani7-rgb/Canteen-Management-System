"""Authoritative intents, full refund requests, and immutable event receipts."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, func
from database import Base

class PaymentIntent(Base):
    __tablename__ = "payment_intents"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, unique=True)
    student_id = Column(String(50), ForeignKey("students.id"), nullable=False, index=True)
    purpose = Column(String(20), nullable=False, default="order", server_default="order")
    idempotency_key = Column(String(128))
    request_fingerprint = Column(String(64))
    provider = Column(String(30), nullable=False)
    amount_paise = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    receipt = Column(String(40), nullable=False, unique=True)
    provider_order_id = Column(String(100), nullable=True, unique=True)
    provider_payment_id = Column(String(100), nullable=True, unique=True)
    provider_refund_id = Column(String(100), nullable=True, unique=True)
    state = Column(String(40), nullable=False, default="created", index=True)
    wallet_credited_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    unrecovered_refund_paise = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        CheckConstraint("amount_paise > 0 AND currency = 'INR'", name="ck_payment_intent_amount"),
        CheckConstraint("(purpose = 'order' AND order_id IS NOT NULL) OR (purpose = 'wallet_topup' AND order_id IS NULL)", name="ck_payment_intent_purpose"),
        CheckConstraint("unrecovered_refund_paise >= 0 AND unrecovered_refund_paise <= amount_paise", name="ck_payment_refund_debt"),
        UniqueConstraint("student_id", "purpose", "idempotency_key", name="uq_payment_intent_idempotency"),
    )

class PaymentRefund(Base):
    __tablename__ = "payment_refunds"
    id = Column(Integer, primary_key=True)
    payment_intent_id = Column(Integer, ForeignKey("payment_intents.id"), nullable=False, unique=True)
    amount_paise = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    idempotency_key = Column(String(64), nullable=False, unique=True)
    receipt = Column(String(40), nullable=False, unique=True)
    provider_refund_id = Column(String(100), unique=True)
    state = Column(String(40), nullable=False, default="created")
    reason = Column(String(255), nullable=False)
    requested_by_admin_id = Column(Integer, ForeignKey("admin_users.id"))
    requested_by_student_id = Column(String(50), ForeignKey("students.id"))
    processed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (CheckConstraint("amount_paise > 0 AND currency = 'INR'", name="ck_payment_refund_amount"),)

class PaymentEvent(Base):
    __tablename__ = "payment_events"
    id = Column(Integer, primary_key=True)
    provider = Column(String(30), nullable=False)
    event_id = Column(String(128), nullable=False)
    body_hash = Column(String(64), nullable=False)
    payment_intent_id = Column(Integer, ForeignKey("payment_intents.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_payment_event_provider_id"),)
