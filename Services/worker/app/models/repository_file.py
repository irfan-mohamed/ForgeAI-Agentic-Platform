"""
repository_file.py — Tracks every file discovered in a connected repository.

Purpose:
  - Records files discovered during each sync pass.
  - Stores a content checksum so the worker can detect which files actually
    changed between syncs (avoiding unnecessary re-embedding).
  - Tracks language/type so the chunker knows how to process the file.
  - Acts as the change-detection layer before the expensive embed step.

Owned by: Worker Service.
"""

import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, BigInteger, Boolean, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FileStatus(str, enum.Enum):
    DISCOVERED = "discovered"   # Found during sync, not yet processed
    INDEXED = "indexed"         # Successfully chunked and embedded
    SKIPPED = "skipped"         # Filtered out (binary, too large, ignored path)
    FAILED = "failed"           # Processing failed for this file
    DELETED = "deleted"         # File was removed from the repository


class RepositoryFile(Base):
    """
    Metadata record for a file within a connected repository.

    One record per (repository_id, path) pair.
    Updated on each sync pass — the checksum is compared to detect changes.

    The actual file content is NOT stored here — it lives in the clone directory
    temporarily during processing, then is discarded.
    """

    __tablename__ = "repository_files"

    __table_args__ = (
        # One record per file path per repository.
        UniqueConstraint("repository_id", "path", name="uq_repo_file_path"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Tenant + repository boundary.
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The file path relative to the repository root (e.g. "src/auth/service.py").
    path: Mapped[str] = mapped_column(String(2048), nullable=False)

    # Detected programming language or document type (e.g. "python", "markdown").
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # File category: "code", "docs", "config", "data", "other".
    file_type: Mapped[str] = mapped_column(String(20), nullable=False, default="other")

    # File size in bytes at last sync.
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # SHA-256 or MD5 hash of the file content at last sync.
    # Used to skip re-processing unchanged files.
    content_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # The commit SHA at which this file was last seen.
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Whether this file has been successfully embedded into the vector DB.
    is_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Current status of this file in the processing pipeline.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=FileStatus.DISCOVERED.value,
    )

    # Total number of chunks created from this file (set after indexing).
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Reason for skipping (if status=SKIPPED).
    skip_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
