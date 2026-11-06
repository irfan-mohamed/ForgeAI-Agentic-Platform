"""
code_relationship.py — Directional relationships between code symbols.

Each row represents one directional edge in the code relationship graph:
    source_symbol → [relationship_type] → target_symbol

Relationship types:
    IMPORTS     — file/module imports a symbol or module
    CALLS       — one function calls another
    DEFINES     — a class defines a method (source=class, target=method)
    REFERENCES  — a symbol references another (non-call use)
    RENDERS     — a React component renders another component
    ROUTES_TO   — a frontend route maps to a component
    HANDLES     — an HTTP route decorator handles a function (FastAPI/Flask)
    USES_API    — a function calls an external HTTP API endpoint

Resolution:
    When first extracted, target_symbol_id may be NULL (unresolved).
    The relationship_resolver pass matches target_symbol_name against
    code_symbols in the same repository and sets target_symbol_id +
    is_resolved=True.

Owned by: Worker Service.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger, Boolean, ForeignKey, Index, Integer, SmallInteger, String, func
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CodeRelationship(Base):
    """
    Directional edge in the code relationship graph.

    Relationship chain:
        Organization → Repository → [source_symbol → type → target_symbol]
    """

    __tablename__ = "code_relationships"

    __table_args__ = (
        Index("ix_rel_source", "source_symbol_id"),
        Index("ix_rel_target", "target_symbol_id"),
        Index("ix_rel_repo", "repository_id"),
        Index("ix_rel_type", "relationship_type"),
        Index("ix_rel_org_repo", "organization_id", "repository_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Tenant + repository boundary
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Version tracking
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # ── Source (always populated) ─────────────────────────────────────────────
    source_symbol_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("code_symbols.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_file_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_line: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Target (may be unresolved until relationship_resolver runs) ───────────
    # target_symbol_id is populated after resolution pass
    target_symbol_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("code_symbols.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # File path of the target (for imports resolved across files)
    target_file_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Raw name extracted from source (used for resolution matching)
    target_symbol_name: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ── Relationship metadata ─────────────────────────────────────────────────
    # IMPORTS|CALLS|DEFINES|REFERENCES|RENDERS|ROUTES_TO|HANDLES|USES_API
    relationship_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # Confidence 0–100. 100 = directly extracted from AST.
    # <100 = heuristic or pattern match.
    confidence: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=100)

    # True once target_symbol_id has been resolved by relationship_resolver
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
