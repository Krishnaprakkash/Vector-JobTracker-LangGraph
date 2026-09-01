"""add hnsw index on resume_chunks.embedding

Revision ID: 0002
Revises: <PUT_PREVIOUS_REVISION_ID>
Create Date: 2026-09-01
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS resume_chunks_embedding_hnsw_idx
        ON resume_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS resume_chunks_embedding_hnsw_idx;")