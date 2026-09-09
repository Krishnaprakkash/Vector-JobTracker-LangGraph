"""drop cover_letters table

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("cover_letters")


def downgrade() -> None:
    op.create_table(
        "cover_letters",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resume_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("iteration_count", sa.Integer(), nullable=False),
        sa.Column("needs_manual_edit", sa.Boolean(), nullable=False),
        sa.Column("pdf_path", sa.String(), nullable=False),
    )