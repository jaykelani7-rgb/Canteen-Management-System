"""Add opt-in lunch configuration; preserve every existing menu/order row."""
from alembic import op
import sqlalchemy as sa

revision = "0007_lunch_bundles"
down_revision = "0006_food_images"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("weekly_menu", sa.Column("sabji_options", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("weekly_menu", sa.Column("ordering_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    raise RuntimeError("Lunch configuration and order snapshots must be preserved; use a reviewed recovery plan")
