"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ENUM as PGEnum
from pgvector.sqlalchemy import Vector

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String, unique=True, index=True, nullable=False),
        sa.Column("last_search_query", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "resumes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "resume_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("resume_id", UUID(as_uuid=True), sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section", sa.String, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
    )
    op.execute(
        "CREATE INDEX resume_chunks_embedding_idx ON resume_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    job_status = PGEnum(
        "browsing", "saved", "applied", "interviewing", "negotiating", "scoring_failed",
        name="jobstatus",
        create_type=False,
    )
    job_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_id", UUID(as_uuid=True), sa.ForeignKey("resumes.id"), nullable=True),
        sa.Column("company", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("dedup_hash", sa.String, unique=True, index=True, nullable=False),
        sa.Column("status", job_status, nullable=False, server_default="browsing"),
        sa.Column("match_score", sa.Float, nullable=True),
        sa.Column("match_rationale", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    PGEnum(name="jobstatus").drop(op.get_bind(), checkfirst=True)
    op.execute("DROP INDEX IF EXISTS resume_chunks_embedding_idx")
    op.drop_table("resume_chunks")
    op.drop_table("resumes")
    op.drop_table("users")