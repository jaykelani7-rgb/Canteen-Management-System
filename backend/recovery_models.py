"""Recovery history contains digests only; the legacy plaintext OTP table is unused."""
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, func, text
from database import Base


class RecoveryChallenge(Base):
    __tablename__ = "recovery_challenges"
    id = Column(String(32), primary_key=True)
    student_id = Column(String(50), ForeignKey("students.id"), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False)
    contact_fingerprint = Column(String(64), nullable=False)
    credential_fingerprint = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="DeliveryPending")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    delivered_at = Column(DateTime(timezone=True))
    finalized_at = Column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("attempts >= 0 AND attempts <= max_attempts AND max_attempts BETWEEN 1 AND 10", name="ck_recovery_attempts"),
        CheckConstraint("status IN ('DeliveryPending','Pending','Consumed','Superseded','Expired','Locked','DeliveryFailed')", name="ck_recovery_status"),
        Index("uq_recovery_active_student", "student_id", unique=True,
              postgresql_where=text("status IN ('DeliveryPending','Pending')"),
              sqlite_where=text("status IN ('DeliveryPending','Pending')")),
    )
