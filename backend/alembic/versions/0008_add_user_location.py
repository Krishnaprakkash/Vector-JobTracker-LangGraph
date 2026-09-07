"""add pending_scoring to jobstatus enum

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("home_location", sa.String(), nullable=True))


def downgrade():
    pass