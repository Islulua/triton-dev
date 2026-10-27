"""Initial multi-user execution/data schema."""

from alembic import op
from triton_dev.platform.models import metadata

revision = "0001_platform"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(bind=op.get_bind())


def downgrade():
    metadata.drop_all(bind=op.get_bind())
