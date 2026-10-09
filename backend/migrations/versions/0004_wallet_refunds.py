"""Add verified wallet top-ups and durable idempotent refunds without replacing data."""
from alembic import op
import sqlalchemy as sa
revision = "0004_wallet_refunds"
down_revision = "0003_payment_records"
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column("payment_intents", "order_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("payment_intents", sa.Column("purpose", sa.String(20), nullable=False, server_default="order"))
    op.add_column("payment_intents", sa.Column("idempotency_key", sa.String(128)))
    op.add_column("payment_intents", sa.Column("request_fingerprint", sa.String(64)))
    op.add_column("payment_intents", sa.Column("wallet_credited_at", sa.DateTime(timezone=True)))
    op.add_column("payment_intents", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.add_column("payment_intents", sa.Column("unrecovered_refund_paise", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_payment_intent_purpose", "payment_intents", "(purpose = 'order' AND order_id IS NOT NULL) OR (purpose = 'wallet_topup' AND order_id IS NULL)")
    op.create_check_constraint("ck_payment_refund_debt", "payment_intents", "unrecovered_refund_paise >= 0 AND unrecovered_refund_paise <= amount_paise")
    op.create_unique_constraint("uq_payment_intent_idempotency", "payment_intents", ["student_id", "purpose", "idempotency_key"])
    op.add_column("wallet_transactions", sa.Column("payment_intent_id", sa.Integer()))
    op.create_foreign_key("fk_wallet_payment_intent", "wallet_transactions", "payment_intents", ["payment_intent_id"], ["id"])
    op.create_index("uq_wallet_payment_success", "wallet_transactions", ["student_id", "payment_intent_id", "transaction_type"], unique=True, postgresql_where=sa.text("payment_intent_id IS NOT NULL AND status = 'success'"))
    op.create_table("payment_refunds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_intent_id", sa.Integer(), sa.ForeignKey("payment_intents.id"), nullable=False, unique=True),
        sa.Column("amount_paise", sa.Integer(), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True), sa.Column("receipt", sa.String(40), nullable=False, unique=True),
        sa.Column("provider_refund_id", sa.String(100), unique=True), sa.Column("state", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("requested_by_admin_id", sa.Integer(), sa.ForeignKey("admin_users.id")),
        sa.Column("requested_by_student_id", sa.String(50), sa.ForeignKey("students.id")),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_paise > 0 AND currency = 'INR'", name="ck_payment_refund_amount"))

def downgrade():
    raise RuntimeError("Financial audit records cannot be discarded; restore a verified backup for rollback")
