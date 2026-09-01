"""add job location/source/comp fields and pinned_companies table

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_jobs_dedup_hash", table_name="jobs")
    op.create_index("ix_jobs_dedup_hash", "jobs", ["dedup_hash"], unique=False)
    op.create_unique_constraint("uq_user_dedup_hash", "jobs", ["user_id", "dedup_hash"])

    op.add_column("jobs", sa.Column("location", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("source", sa.String(), nullable=False, server_default="ddgs"))
    op.add_column("jobs", sa.Column("comp_min", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("comp_max", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("comp_currency", sa.String(), nullable=True))
    op.add_column("jobs", sa.Column("comp_estimated", sa.Boolean(), nullable=False, server_default="false"))
    op.alter_column("jobs", "source", server_default=None)
    op.alter_column("jobs", "comp_estimated", server_default=None)

    op.create_table(
        "pinned_companies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_slug", sa.String(), nullable=False),
        sa.Column("ats_source", sa.String(), nullable=False),
        sa.UniqueConstraint("user_id", "company_slug", "ats_source", name="uq_pinned_company"),
    )


def downgrade():
    op.drop_table("pinned_companies")
    op.drop_column("jobs", "comp_estimated")
    op.drop_column("jobs", "comp_currency")
    op.drop_column("jobs", "comp_max")
    op.drop_column("jobs", "comp_min")
    op.drop_column("jobs", "source")
    op.drop_column("jobs", "location")
    op.drop_constraint("uq_user_dedup_hash", "jobs", type_="unique")
    op.drop_index("ix_jobs_dedup_hash", table_name="jobs")
    op.create_index("ix_jobs_dedup_hash", "jobs", ["dedup_hash"], unique=True)