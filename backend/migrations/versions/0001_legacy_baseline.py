"""Frozen original schema; new databases only. Existing databases use checked adoption."""
from alembic import op
from migrations.legacy_schema import Base
revision = "0001_legacy_baseline"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=False)

def downgrade():
    raise RuntimeError("Refusing to drop application tables; restore a verified backup through an explicit recovery plan")
