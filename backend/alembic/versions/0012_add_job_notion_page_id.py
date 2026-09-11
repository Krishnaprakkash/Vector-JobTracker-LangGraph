"""add job notion_page_id

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("notion_page_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "notion_page_id")