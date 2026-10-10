"""Add persistent optimized photographs without changing existing menu/order rows."""
from alembic import op
import sqlalchemy as sa

revision = "0006_food_images"
down_revision = "0005_secure_recovery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("food_images",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("dish_name", sa.String(100), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(30), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False), sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(1000), nullable=False), sa.Column("license", sa.String(200), nullable=False),
        sa.Column("license_url", sa.String(1000)), sa.Column("author", sa.String(200)),
        sa.Column("attribution", sa.Text(), nullable=False), sa.Column("modifications", sa.String(255), nullable=False),
        sa.Column("rights_confirmed", sa.Boolean(), nullable=False),
        sa.Column("uploaded_by_admin_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("byte_size > 0 AND byte_size <= 327680 AND length(data) = byte_size", name="ck_food_image_bytes"),
        sa.CheckConstraint("width BETWEEN 64 AND 1280 AND height BETWEEN 64 AND 1280", name="ck_food_image_dimensions"),
        sa.CheckConstraint("mime_type = 'image/webp' AND rights_confirmed", name="ck_food_image_validated"))
    op.create_index("ix_food_images_dish_name", "food_images", ["dish_name"])
    op.add_column("food_items", sa.Column("image_id", sa.String(32), nullable=True))
    op.add_column("food_items", sa.Column("image_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_foreign_key("fk_food_item_image", "food_items", "food_images", ["image_id"], ["id"])
    op.create_index("ix_food_items_image_id", "food_items", ["image_id"])


def downgrade():
    raise RuntimeError("Photographs and historical associations must be preserved; use a reviewed recovery plan")
