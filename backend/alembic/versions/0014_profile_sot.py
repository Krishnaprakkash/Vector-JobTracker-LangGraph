"""profile source-of-truth: Profile/ProfileItem/ProfileChunk, repurpose Resume, rename Job.resume_id

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

profile_section_enum = postgresql.ENUM(
    "skills", "experience", "education", "projects", "certifications",
    name="profilesection",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    profile_section_enum.create(bind, checkfirst=True)

    op.add_column("users", sa.Column("notion_profile_db_id", sa.String(), nullable=True))

    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "profile_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section", profile_section_enum, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("notion_page_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "profile_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section", profile_section_enum, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.UniqueConstraint("profile_id", "section", name="uq_profile_section"),
    )
    op.execute("ALTER TABLE profile_chunks ADD COLUMN embedding vector(768) NOT NULL")
    op.drop_table("resume_chunks")

    op.drop_column("resumes", "summary")
    op.add_column("resumes", sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("resumes", sa.Column("pdf_path", sa.String(), nullable=True))
    op.execute("UPDATE jobs SET resume_id = NULL")
    op.execute("DELETE FROM resumes")
    op.alter_column("resumes", "job_id", nullable=False)
    op.alter_column("resumes", "pdf_path", nullable=False)
    op.create_foreign_key("fk_resumes_job_id", "resumes", "jobs", ["job_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    op.alter_column("jobs", "optimized_resume_id", new_column_name="resume_id")
    op.drop_constraint("fk_resumes_job_id", "resumes", type_="foreignkey")
    op.drop_column("resumes", "pdf_path")
    op.drop_column("resumes", "job_id")
    op.add_column("resumes", sa.Column("summary", sa.Text(), nullable=True))

    op.create_table(
        "resume_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resume_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.execute("ALTER TABLE resume_chunks ADD COLUMN embedding vector(768) NOT NULL")

    op.drop_table("profile_chunks")
    op.drop_table("profile_items")
    op.drop_table("profiles")
    op.drop_column("users", "notion_profile_db_id")
    profile_section_enum.drop(op.get_bind(), checkfirst=True)