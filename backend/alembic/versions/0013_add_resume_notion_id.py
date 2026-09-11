"""add resume notion_page_id

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("resumes", sa.Column("notion_page_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("resumes", "notion_page_id")