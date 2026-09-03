"""add pending_scoring to jobstatus enum

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-03
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'pending_scoring'")


def downgrade():
    pass