"""SQLAlchemy tables for the SaaS layer.

- User: accounts (email + bcrypt password hash).
- ProviderKey: a user's own LLM keys (OpenAI/Anthropic/Gemini), Fernet-encrypted.
- CustomEndpoint: any OpenAI-compatible / Ollama endpoint the user adds.
- StudyResult: one participant's timed task in the newcomer user study.
- Repo / RepoFile / RepoChunk / RepoArtifact: indexed snapshots, owned by a user.
  Chunk embeddings live in the Postgres-only `chunk_embeddings` table (pgvector,
  keyed by content hash) created by migration 0002 and queried with raw SQL.
- UsageCounter: per-user daily quotas.
- EmailOtp: one-time sign-in / sign-up codes (only a keyed hash of the code is stored).
- IngestJob: a background ingestion of an uploaded codebase (ZIP, folder or CLI).
"""
import uuid
from datetime import datetime

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, LargeBinary,
                        String, Text, false, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uid() -> str:
    return uuid.uuid4().hex[:16]


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[int] = mapped_column(default=1)
    email_verified: Mapped[int] = mapped_column(Integer, default=0)
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    provider_keys: Mapped[list["ProviderKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")
    endpoints: Mapped[list["CustomEndpoint"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")


class ProviderKey(Base):
    __tablename__ = "provider_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         index=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    provider: Mapped[str] = mapped_column(String(32), index=True)  # openai|anthropic|gemini
    model: Mapped[str] = mapped_column(String(120), default="")
    key_enc: Mapped[str] = mapped_column(Text)  # Fernet ciphertext
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    user: Mapped[User] = relationship(back_populates="provider_keys")


class CustomEndpoint(Base):
    __tablename__ = "custom_endpoints"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    base_url: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(32), default="openai-compatible")
    model: Mapped[str] = mapped_column(String(120), default="")
    api_key_enc: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    user: Mapped[User] = relationship(back_populates="endpoints")


class StudyResult(Base):
    """One timed task by one participant (control = repo only, sherpa = repo + Sherpa)."""
    __tablename__ = "study_results"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    participant: Mapped[str] = mapped_column(String(60))      # pseudonym, e.g. P3 — no real names
    group: Mapped[str] = mapped_column(String(16), index=True)  # control | sherpa
    task: Mapped[str] = mapped_column(String(32), index=True)   # architecture | flow | starter
    repo: Mapped[str] = mapped_column(String(200), default="")
    seconds: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float, default=0)
    max_score: Mapped[float] = mapped_column(Float, default=1)
    useful: Mapped[int] = mapped_column(Integer, default=0)       # 1-5, sherpa group only
    trustworthy: Mapped[int] = mapped_column(Integer, default=0)  # 1-5
    reuse: Mapped[int] = mapped_column(Integer, default=0)        # 1-5
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class Repo(Base):
    """One indexed snapshot. `version` bumps on every re-index so caches can tell it changed."""
    __tablename__ = "repos"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[str] = mapped_column(String(1000), default="")
    kind: Mapped[str] = mapped_column(String(16), default="git")  # git | local | self
    branch: Mapped[str] = mapped_column(String(200), default="")
    commit: Mapped[str] = mapped_column(String(64), default="")
    indexed_at: Mapped[float] = mapped_column(Float, default=0)
    files_count: Mapped[int] = mapped_column(Integer, default=0)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # roles, file_hashes, …
    version: Mapped[int] = mapped_column(Integer, default=0)
    # private mode (app/private.py): code lives in memory only; the row is deleted at expires_at
    private: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    expires_at: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class RepoFile(Base):
    __tablename__ = "repo_files"

    repo_id: Mapped[str] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), primary_key=True)
    path: Mapped[str] = mapped_column(String(1000), primary_key=True)
    hash: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)


class RepoChunk(Base):
    __tablename__ = "repo_chunks"
    __table_args__ = (Index("ix_repo_chunks_repo_ord", "repo_id", "ord"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"))
    ord: Mapped[int] = mapped_column(Integer)
    file: Mapped[str] = mapped_column(String(1000))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32), default="code")
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(40), index=True)  # → chunk_embeddings


class RepoArtifact(Base):
    """Cached agent output (overview, tasks, docs) for a repo."""
    __tablename__ = "repo_artifacts"

    repo_id: Mapped[str] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now(), onupdate=func.now())


class UsageCounter(Base):
    __tablename__ = "usage_counters"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD (UTC)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)  # llm | ingest
    count: Mapped[int] = mapped_column(Integer, default=0)


class EmailOtp(Base):
    __tablename__ = "email_otps"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    email: Mapped[str] = mapped_column(String(320), index=True)
    purpose: Mapped[str] = mapped_column(String(16))  # login | signup
    name: Mapped[str] = mapped_column(String(120), default="")
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[float] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float)


class IngestJob(Base):
    """review → queued → processing → ready | failed. `payload` holds the accepted files
    (gzipped JSON) so a failed job can be retried without uploading again; it is cleared
    once the job succeeds."""
    __tablename__ = "ingest_jobs"
    __table_args__ = (Index("ix_ingest_jobs_user", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    repo_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    origin: Mapped[str] = mapped_column(String(16), default="zip")  # zip | folder | cli
    status: Mapped[str] = mapped_column(String(16))
    stage: Mapped[str] = mapped_column(String(32), default="")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(Text, default="")
    manifest: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
