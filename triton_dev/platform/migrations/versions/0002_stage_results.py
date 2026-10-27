"""Normalized case stage indexes for phase-level queries."""

from alembic import op
from triton_dev.platform.models import stage_results

revision = "0002_stage_results"
down_revision = "0001_platform"
branch_labels = None
depends_on = None


def upgrade():
    stage_results.create(op.get_bind(), checkfirst=True)


def downgrade():
    stage_results.drop(op.get_bind(), checkfirst=True)
