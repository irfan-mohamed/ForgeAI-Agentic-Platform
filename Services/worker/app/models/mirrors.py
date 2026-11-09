"""
mirrors.py — Read-only SQLAlchemy models for tables owned by other services.

The Worker needs to READ from:
  - repositories        (owned by Repository Service)
  - repository_syncs    (owned by Repository Service — worker WRITES progress here too)
  - github_installations (owned by Repository Service)

We define lightweight ORM classes here to query these tables without
importing models from another service (which would create coupling).

IMPORTANT:
  - The Worker must NOT call Base.metadata.create_all() for these tables.
  - Only the Repository Service creates/migrates these tables.
  - We mark them with __table_args__ = {'extend_existing': True} to prevent
    re-registration conflicts if both services ever share a Python process in tests.
"""

import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, BigInteger, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


# ── Enums (must match Repository Service exactly) ─────────────────────────────

class RepositoryStatus(str, enum.Enum):
    CONNECTING = "connecting"
    SYNCING = "syncing"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    ACCESS_REVOKED = "access_revoked"
    DISCONNECTED = "disconnected"


class SyncStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SyncTrigger(str, enum.Enum):
    INITIAL = "initial"
    MANUAL = "manual"
    WEBHOOK_PUSH = "webhook_push"


class InstallationStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


# ── Mirror Models ─────────────────────────────────────────────────────────────

class GitHubInstallation(Base):
    """Read-only mirror of the github_installations table (owned by repository service)."""
    __tablename__ = "github_installations"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False)
    github_installation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    github_account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class Repository(Base):
    """Read-only mirror of the repositories table (owned by repository service)."""
    __tablename__ = "repositories"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False)
    github_installation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("github_installations.id"),
        nullable=False,
    )
    github_repository_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    # Readiness checkpoints written by the worker pipeline.
    repo_map_ready_at: Mapped[datetime | None] = mapped_column(nullable=True)
    chat_ready_at: Mapped[datetime | None] = mapped_column(nullable=True)
    index_ready_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)


class RepositorySync(Base):
    """
    Mirror of repository_syncs table.
    The Worker WRITES to this table to update sync progress.
    The Repository Service owns the table schema.
    """
    __tablename__ = "repository_syncs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    files_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
