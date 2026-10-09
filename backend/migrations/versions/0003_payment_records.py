"""Durable provider intents and webhook receipts; no existing records deleted."""
from alembic import op
import sqlalchemy as sa
revision="0003_payment_records"
down_revision="0002_production_hardening"
branch_labels=None
depends_on=None

def upgrade():
    op.execute(sa.schema.CreateSequence(sa.Sequence("canteen_order_number_seq", start=1001)))
    op.execute(sa.text("SELECT setval('canteen_order_number_seq', GREATEST(1000, COALESCE((SELECT MAX(CAST(SUBSTRING(order_number FROM 2) AS BIGINT)) FROM orders WHERE order_number ~ '^#[0-9]{1,15}$'),1000), COALESCE((SELECT MAX(id)+1000 FROM orders),1000)), true)"))
    op.create_table("payment_intents",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("order_id",sa.Integer(),sa.ForeignKey("orders.id"),nullable=False,unique=True),sa.Column("student_id",sa.String(50),sa.ForeignKey("students.id"),nullable=False),sa.Column("provider",sa.String(30),nullable=False),sa.Column("amount_paise",sa.Integer(),nullable=False),sa.Column("currency",sa.String(3),nullable=False),sa.Column("receipt",sa.String(40),nullable=False,unique=True),sa.Column("provider_order_id",sa.String(100),unique=True),sa.Column("provider_payment_id",sa.String(100),unique=True),sa.Column("provider_refund_id",sa.String(100),unique=True),sa.Column("state",sa.String(40),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.CheckConstraint("amount_paise > 0 AND currency = 'INR'",name="ck_payment_intent_amount"))
    op.create_index("ix_payment_intents_student_id","payment_intents",["student_id"])
    op.create_index("ix_payment_intents_state","payment_intents",["state"])
    op.create_table("payment_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("provider",sa.String(30),nullable=False),sa.Column("event_id",sa.String(128),nullable=False),sa.Column("body_hash",sa.String(64),nullable=False),sa.Column("payment_intent_id",sa.Integer(),sa.ForeignKey("payment_intents.id")),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.UniqueConstraint("provider","event_id",name="uq_payment_event_provider_id"))

def downgrade():
    raise RuntimeError("Payment audit records cannot be discarded; restore a verified backup for rollback")
