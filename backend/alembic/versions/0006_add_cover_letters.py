"""create cover_letters table

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cover_letters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_id", UUID(as_uuid=True), sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("iteration_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("needs_manual_edit", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("pdf_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("cover_letters")