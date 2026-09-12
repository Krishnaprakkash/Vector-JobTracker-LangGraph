"""add notion data_source_id columns for 2026-03-11 API upgrade

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("notion_jobs_data_source_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("notion_resumes_data_source_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("notion_settings_data_source_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("notion_profile_data_source_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "notion_profile_data_source_id")
    op.drop_column("users", "notion_settings_data_source_id")
    op.drop_column("users", "notion_resumes_data_source_id")
    op.drop_column("users", "notion_jobs_data_source_id")