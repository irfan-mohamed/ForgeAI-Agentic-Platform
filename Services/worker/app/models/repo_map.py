"""
repo_map.py — RepositoryMap model mirror for the Worker Service.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Integer, String, Text, JSON, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class RepositoryMap(Base):
    __tablename__ = "repository_maps"
    __table_args__ = (
        UniqueConstraint("organization_id", "repository_id", name="uq_repo_map_org_repo"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    repository_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    commit_sha: Mapped[str | None] = mapped_column(String(100), nullable=True)

    file_tree: Mapped[list | None] = mapped_column(_JSON_TYPE, nullable=True)
    languages: Mapped[dict | None] = mapped_column(_JSON_TYPE, nullable=True)
    symbols_summary: Mapped[list | None] = mapped_column(_JSON_TYPE, nullable=True)
    imports: Mapped[list | None] = mapped_column(_JSON_TYPE, nullable=True)
    routes: Mapped[list | None] = mapped_column(_JSON_TYPE, nullable=True)
    test_files: Mapped[list | None] = mapped_column(_JSON_TYPE, nullable=True)
    doc_files: Mapped[list | None] = mapped_column(_JSON_TYPE, nullable=True)

    raw_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)

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
