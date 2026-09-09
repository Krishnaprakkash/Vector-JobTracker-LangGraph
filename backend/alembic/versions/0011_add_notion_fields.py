"""add experience_level (model catch-up) + notion oauth fields

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "email", nullable=True)
    op.add_column("users", sa.Column("notion_workspace_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("notion_access_token", sa.String(), nullable=True))
    op.add_column("users", sa.Column("notion_bot_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("notion_jobs_db_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("notion_resumes_db_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("notion_settings_db_id", sa.String(), nullable=True))
    op.create_unique_constraint("uq_users_notion_workspace_id", "users", ["notion_workspace_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_notion_workspace_id", "users", type_="unique")
    op.drop_column("users", "notion_settings_db_id")
    op.drop_column("users", "notion_resumes_db_id")
    op.drop_column("users", "notion_jobs_db_id")
    op.drop_column("users", "notion_bot_id")
    op.drop_column("users", "notion_access_token")
    op.drop_column("users", "notion_workspace_id")
    op.alter_column("users", "email", nullable=False)