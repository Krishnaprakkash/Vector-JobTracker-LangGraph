"""drop known_companies and pinned_companies tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

def upgrade():
    op.drop_table("known_companies")
    op.drop_table("pinned_companies")

def downgrade():
    # recreate both if ever needed — omitted here for brevity, not expected to be used
    pass