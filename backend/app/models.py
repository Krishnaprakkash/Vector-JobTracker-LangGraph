import uuid
from datetime import datetime

from sqlalchemy import String, Text, ForeignKey, DateTime, UniqueConstraint, func, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
import enum

from app.db import Base


class JobStatus(str, enum.Enum):
    browsing = "browsing"
    pending_scoring = "pending_scoring"
    saved = "saved"
    applied = "applied"
    interviewing = "interviewing"
    negotiating = "negotiating"
    scoring_failed = "scoring_failed"


class ProfileSection(str, enum.Enum):
    skills = "skills"
    experience = "experience"
    education = "education"
    projects = "projects"
    certifications = "certifications"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    last_search_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    resumes: Mapped[list["Resume"]] = relationship(back_populates="user")
    jobs: Mapped[list["Job"]] = relationship(back_populates="user")
    home_location: Mapped[str | None] = mapped_column(String, nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String, nullable=True)

    notion_workspace_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    notion_access_token: Mapped[str | None] = mapped_column(String, nullable=True)
    notion_bot_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notion_jobs_db_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notion_jobs_data_source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notion_resumes_db_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notion_resumes_data_source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notion_settings_db_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notion_settings_data_source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notion_profile_db_id: Mapped[str | None] = mapped_column(String, nullable=True)
    notion_profile_data_source_id: Mapped[str | None] = mapped_column(String, nullable=True)

    profile: Mapped["Profile | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class Resume(Base):
    """Terminal artifact: per-job Optimizer-generated PDF output only. Never chunked/embedded."""
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String)
    pdf_path: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="resumes")

    notion_page_id: Mapped[str | None] = mapped_column(String, nullable=True)


class Profile(Base):
    """Singular per-user canonical source of truth for matching + resume optimization."""
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="profile")
    items: Mapped[list["ProfileItem"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    chunks: Mapped[list["ProfileChunk"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class ProfileItem(Base):
    """One user-entered fact within a Profile section (Notion-sourced)."""
    __tablename__ = "profile_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    section: Mapped[ProfileSection] = mapped_column(SAEnum(ProfileSection))
    content: Mapped[str] = mapped_column(Text)
    notion_page_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile: Mapped["Profile"] = relationship(back_populates="items")


class ProfileChunk(Base):
    """One row per section: synthetic concatenated section text + embedding. Replaces ResumeChunk."""
    __tablename__ = "profile_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    section: Mapped[ProfileSection] = mapped_column(SAEnum(ProfileSection))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(768))

    profile: Mapped["Profile"] = relationship(back_populates="chunks")
    __table_args__ = (UniqueConstraint("profile_id", "section", name="uq_profile_section"),)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    optimized_resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resumes.id"), nullable=True)

    company: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String)  # greenhouse | lever | ashby | ddgs
    comp_min: Mapped[int | None] = mapped_column(nullable=True)
    comp_max: Mapped[int | None] = mapped_column(nullable=True)
    comp_currency: Mapped[str | None] = mapped_column(String, nullable=True)
    comp_estimated: Mapped[bool] = mapped_column(default=False)

    dedup_hash: Mapped[str] = mapped_column(String, index=True)

    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus), default=JobStatus.browsing)
    match_score: Mapped[float | None] = mapped_column(nullable=True)
    match_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    notion_page_id: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped["User"] = relationship(back_populates="jobs")
    __table_args__ = (UniqueConstraint("user_id", "dedup_hash", name="uq_user_dedup_hash"),)