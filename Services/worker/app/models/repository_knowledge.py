"""
repository_knowledge.py — PostgreSQL metadata for vector knowledge chunks.

Purpose:
  Every chunk that gets embedded and stored in Qdrant also has a lightweight
  metadata record here. This allows:
    1. Source traceability — "this answer came from file X, chunk Y"
    2. Cleanup — when a repo is disconnected, we can find and delete all
       its Qdrant vectors using the stored vector_id references.
    3. Re-indexing detection — we can check if a chunk is still current
       by comparing the commit_sha.
    4. Tenant isolation enforcement — organization_id is always stored
       so we can filter vectors at the metadata level in Qdrant.

The VECTOR itself lives in Qdrant.
This table stores everything about WHERE and WHAT was embedded.

Owned by: Worker Service.
"""

from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RepositoryKnowledge(Base):
    """
    One record per chunk embedded into the vector database.

    Relationship chain for traceability:
        Organization → Repository → File → Chunk → Vector
    """

    __tablename__ = "repository_knowledge"

    __table_args__ = (
        # Fast lookup: "give me all chunks for this file"
        Index("ix_rk_repository_file", "repository_id", "file_path"),
        # Fast lookup: "give me all chunks for this org"
        Index("ix_rk_organization", "organization_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Tenant isolation — always filter on this.
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Which repository this chunk came from.
    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # FK to repository_files — links chunk back to its source file record.
    repository_file_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repository_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # File path relative to repo root (denormalized for fast queries).
    file_path: Mapped[str] = mapped_column(String(2048), nullable=False)

    # Commit SHA at the time this chunk was embedded.
    # Allows detecting stale knowledge when a new sync comes in.
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Detected language (e.g. "python", "typescript", "markdown").
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Chunk type: "function", "class", "method", "module", "block", "doc_section".
    # Describes the semantic unit of code/text that was chunked.
    chunk_type: Mapped[str] = mapped_column(String(30), nullable=False, default="block")

    # Human-readable name for this chunk (e.g. function/class name if detected).
    chunk_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Zero-based sequence index within the file (chunk 0, chunk 1, ...).
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Line range in the source file (for citation purposes).
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # The actual text content of this chunk (stored for re-display / citation).
    # Stored as Text (unlimited) — typical chunks are ~200-500 tokens.
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Token count of the chunk content (for observability/debugging).
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Unique ID of the vector in Qdrant for this chunk.
    # Used to update/delete the vector during re-sync or cleanup.
    vector_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)

    # The embedding model used (for future model migration detection).
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)

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
