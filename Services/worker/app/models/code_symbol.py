"""
code_symbol.py — PostgreSQL model for extracted code symbols.

A code symbol is any named entity extracted from source code via
tree-sitter AST parsing: functions, methods, classes, variables,
imports, exports, and route handlers.

One row per symbol per file per commit. On re-sync, old symbols for
a file are deleted and re-extracted.

Purpose:
  1. Lexical/structural search — find "login" by name, not just semantics.
  2. Relationship source — code_relationships links symbols to each other.
  3. Context assembly — retrieve the exact signature + docstring without
     fetching the whole file.
  4. Route tracing — symbol_type='route' enables frontend→backend tracing.

Owned by: Worker Service.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger, Boolean, ForeignKey, Index, Integer, String, Text, func
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CodeSymbol(Base):
    """
    One extracted code symbol from a repository file.

    Relationship chain for traceability:
        Organization → Repository → File → Symbol
    """

    __tablename__ = "code_symbols"

    __table_args__ = (
        # Fast lookup: all symbols in one file
        Index("ix_syms_repo_file", "repository_id", "file_path"),
        # Fast lookup: all symbols in one org
        Index("ix_syms_org", "organization_id"),
        # Fast lookup: find by name (exact match / LIKE)
        Index("ix_syms_name", "symbol_name"),
        # Fast lookup: find by qualified name
        Index("ix_syms_qname", "qualified_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Tenant + repository boundary
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_file_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repository_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Version tracking — set to commit SHA at time of extraction
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Source location
    file_path: Mapped[str] = mapped_column(String(2048), nullable=False)

    # Symbol identity
    symbol_name: Mapped[str] = mapped_column(String(512), nullable=False)
    # Qualified name includes enclosing class/module: "MyClass.my_method"
    qualified_name: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Symbol category
    # function | method | class | variable | import | export | route
    symbol_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # Language detected by file_filter (e.g. "python", "typescript")
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Line range in the source file
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Full function/method/class signature line (first line of definition)
    # e.g. "def login(email: str, password: str) -> User:"
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)

    # First docstring / JSDoc comment, if any
    docstring: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Modifier flags
    is_exported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_async: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # For methods inside classes, points to the parent class symbol
    parent_symbol_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("code_symbols.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

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
