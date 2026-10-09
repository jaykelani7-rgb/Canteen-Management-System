"""Add secure recovery audit history without changing legacy users or OTP records."""
from alembic import op
import sqlalchemy as sa
revision = "0005_secure_recovery"
down_revision = "0004_wallet_refunds"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("recovery_challenges",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("student_id", sa.String(50), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("contact_fingerprint", sa.String(64), nullable=False),
        sa.Column("credential_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("attempts >= 0 AND attempts <= max_attempts AND max_attempts BETWEEN 1 AND 10", name="ck_recovery_attempts"),
        sa.CheckConstraint("status IN ('DeliveryPending','Pending','Consumed','Superseded','Expired','Locked','DeliveryFailed')", name="ck_recovery_status"))
    op.create_index("ix_recovery_challenges_student_id", "recovery_challenges", ["student_id"])
    op.create_index("uq_recovery_active_student", "recovery_challenges", ["student_id"], unique=True,
                    postgresql_where=sa.text("status IN ('DeliveryPending','Pending')"),
                    sqlite_where=sa.text("status IN ('DeliveryPending','Pending')"))


def downgrade():
    raise RuntimeError("Recovery audit history must not be discarded; use a reviewed rollback plan")
