"""Non-destructive money, idempotency, ledger and notification receipt hardening."""
from alembic import op
import sqlalchemy as sa
from migrations.preflight import MONEY, validate_financial_data
revision = "0002_production_hardening"
down_revision = "0001_legacy_baseline"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("Production migrations require PostgreSQL; do not use SQLite to validate financial migrations")
    validate_financial_data(bind)
    for table, columns in MONEY.items():
        for column in columns:
            op.alter_column(table,column,existing_type=sa.Float(),type_=sa.Numeric(12,2),existing_nullable=False,postgresql_using=f"round({column}::numeric,2)")
    op.alter_column("students","wallet_balance",server_default=sa.text("0"))
    checks = {
        "ala_carte":("ck_ala_carte_price","price >= 0 AND price < 10000000000"),
        "food_items":("ck_food_items_price","price >= 0 AND price < 10000000000"),
        "students":("ck_students_money","wallet_balance >= 0 AND wallet_balance < 10000000000 AND total_spent >= 0 AND total_spent < 10000000000"),
        "orders":("ck_orders_money","item_total >= 0 AND packaging_fee >= 0 AND gst_amount >= 0 AND total_amount >= 0 AND total_amount < 10000000000"),
        "wallet_transactions":("ck_wallet_transactions_amount","amount >= 0 AND amount < 10000000000"),
    }
    for table,(name,expression) in checks.items():
        op.create_check_constraint(name,table,expression)
    op.add_column("orders",sa.Column("idempotency_key",sa.String(128),nullable=True))
    op.add_column("orders",sa.Column("request_fingerprint",sa.String(64),nullable=True))
    op.create_unique_constraint("uq_orders_student_idempotency","orders",["student_id","idempotency_key"])
    op.create_foreign_key("fk_wallet_transactions_order_id","wallet_transactions","orders",["order_id"],["id"])
    op.create_foreign_key("fk_notifications_order_id","notifications","orders",["order_id"],["id"])
    op.create_index("uq_wallet_order_success","wallet_transactions",["student_id","order_id","transaction_type"],unique=True,postgresql_where=sa.text("order_id IS NOT NULL AND status = 'success'"))
    op.create_table("notification_reads",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("student_id",sa.String(50),sa.ForeignKey("students.id",ondelete="CASCADE"),nullable=False),
        sa.Column("notification_id",sa.Integer(),sa.ForeignKey("notifications.id",ondelete="CASCADE"),nullable=False),
        sa.Column("read_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.UniqueConstraint("student_id","notification_id",name="uq_notification_reads_student_notification"))
    op.create_index("ix_notification_reads_student_id","notification_reads",["student_id"])
    op.create_index("ix_notification_reads_notification_id","notification_reads",["notification_id"])

def downgrade():
    raise RuntimeError("Hardening downgrade could discard audit/idempotency data; use an explicitly reviewed backup recovery plan")
