"""Daily plans, normalized case reports and database log contents."""

from alembic import op
from triton_dev.platform.models import daily_plans, daily_cases, daily_logs

revision = "0003_daily"
down_revision = "0002_stage_results"
branch_labels = None
depends_on = None


def upgrade():
    for table in (daily_plans, daily_cases, daily_logs):
        table.create(op.get_bind(), checkfirst=True)


def downgrade():
    for table in (daily_logs, daily_cases, daily_plans):
        table.drop(op.get_bind(), checkfirst=True)
