"""
internal.py — Repository Intelligence Internal API.

Provides structured access to the code graph extracted from indexed repositories:
  - Symbol search (lexical + optional filter by type/language)
  - Symbol lookup (single symbol detail with signature, docstring, line range)
  - Callers graph  (which symbols call a given symbol)
  - Callees graph  (which symbols a given symbol calls)
  - References     (which files/symbols import or reference a symbol)
  - Route catalog  (all HTTP routes in the repository)
  - File structure (directory tree of indexed files)
  - Index status   (per-repository indexing health)

Security model:
  - All endpoints require a valid JWT (Bearer token).
  - Org membership is verified via the shared memberships table.
  - All queries filter on organization_id AND repository_id to enforce
    tenant isolation. Results from other orgs cannot bleed through.

These endpoints are consumed by:
  1. The AI service for context assembly in Phase 3 (agentic tools).
  2. Frontend for repository explorer UI.

Owned by: Repository Service.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user_id, get_org_membership
from app.db.database import get_db
from app.models.repository import Repository, RepositoryStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal",
    tags=["Internal — Repository Intelligence"],
)


# ── Pydantic response models ──────────────────────────────────────────────────

class SymbolSummary(BaseModel):
    id: int
    symbol_name: str
    qualified_name: Optional[str]
    symbol_type: str
    file_path: str
    start_line: Optional[int]
    end_line: Optional[int]
    language: Optional[str]
    is_async: bool
    is_exported: bool
    signature: Optional[str]


class SymbolDetail(SymbolSummary):
    docstring: Optional[str]
    parent_symbol_id: Optional[int]


class RelationshipEdge(BaseModel):
    source_symbol_id: Optional[int]
    source_symbol_name: Optional[str]
    source_file_path: str
    source_line: Optional[int]
    target_symbol_id: Optional[int]
    target_symbol_name: Optional[str]
    target_file_path: Optional[str]
    relationship_type: str
    confidence: int
    is_resolved: bool


class RouteEntry(BaseModel):
    symbol_name: str       # e.g. "GET /api/users"
    qualified_name: Optional[str]
    file_path: str
    start_line: Optional[int]
    signature: Optional[str]
    # The handler function this route HANDLES (if resolved)
    handler_symbol_id: Optional[int]
    handler_symbol_name: Optional[str]
    handler_file_path: Optional[str]


class FileEntry(BaseModel):
    path: str
    language: Optional[str]
    is_indexed: bool
    chunk_count: Optional[int]
    size_bytes: Optional[int]


class IndexStatus(BaseModel):
    repository_id: int
    status: str
    total_files: int
    indexed_files: int
    failed_files: int
    total_symbols: int
    resolved_relationships: int
    unresolved_relationships: int
    total_relationships: int
    last_synced_at: Optional[str]


# ── Repository access guard ───────────────────────────────────────────────────

def _get_ready_repository(
    org_id: int,
    repository_id: int,
    db: Session,
    require_ready: bool = True,
) -> Repository:
    """Loads and validates repository access. Raises 404/409 on failure."""
    repo = (
        db.query(Repository)
        .filter(
            Repository.id == repository_id,
            Repository.organization_id == org_id,
        )
        .first()
    )
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    if require_ready and repo.status != RepositoryStatus.READY.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository is not ready for queries (status: {repo.status})",
        )
    return repo


# ── 1. Symbol Search ──────────────────────────────────────────────────────────

@router.get(
    "/organizations/{org_id}/repositories/{repository_id}/symbols/search",
    response_model=list[SymbolSummary],
    summary="Search symbols by name (FTS + optional filters)",
)
def search_symbols(
    org_id: int,
    repository_id: int,
    q: str = Query(..., min_length=1, description="Search term (name, qualified name, signature)"),
    symbol_type: Optional[str] = Query(None, description="Filter: function|method|class|route|import"),
    language: Optional[str] = Query(None, description="Filter: python|javascript|typescript"),
    limit: int = Query(20, ge=1, le=100),
    user_id: int = Depends(get_org_membership),
    db: Session = Depends(get_db),
) -> list[SymbolSummary]:
    """
    Full-text search over code symbols in a repository.

    Uses PostgreSQL FTS (tsvector) for lexical matching. Falls back to
    ILIKE if tsvector is not yet populated.
    """
    _get_ready_repository(org_id, repository_id, db)

    params: dict = {
        "repo_id": repository_id,
        "org_id": org_id,
        "limit": limit,
        "q": q,
    }

    # Try FTS first; fall back to ILIKE if search_vector column not found
    try:
        sql = """
            SELECT
                id, symbol_name, qualified_name, symbol_type, file_path,
                start_line, end_line, language, is_async, is_exported, signature
            FROM code_symbols
            WHERE
                organization_id = :org_id
                AND repository_id = :repo_id
                {type_filter}
                {lang_filter}
                AND search_vector @@ plainto_tsquery('english', :q)
            ORDER BY ts_rank(search_vector, plainto_tsquery('english', :q)) DESC
            LIMIT :limit
        """
    except Exception:
        sql = """
            SELECT
                id, symbol_name, qualified_name, symbol_type, file_path,
                start_line, end_line, language, is_async, is_exported, signature
            FROM code_symbols
            WHERE
                organization_id = :org_id
                AND repository_id = :repo_id
                {type_filter}
                {lang_filter}
                AND (symbol_name ILIKE :q_ilike OR qualified_name ILIKE :q_ilike)
            LIMIT :limit
        """
        params["q_ilike"] = f"%{q}%"

    type_filter = "AND symbol_type = :symbol_type" if symbol_type else ""
    lang_filter = "AND language = :language" if language else ""

    if symbol_type:
        params["symbol_type"] = symbol_type
    if language:
        params["language"] = language

    final_sql = sql.format(type_filter=type_filter, lang_filter=lang_filter)

    rows = db.execute(text(final_sql), params).fetchall()
    return [SymbolSummary(**dict(r._mapping)) for r in rows]


# ── 2. Symbol Detail ──────────────────────────────────────────────────────────

@router.get(
    "/organizations/{org_id}/repositories/{repository_id}/symbols/{symbol_id}",
    response_model=SymbolDetail,
    summary="Get full detail for a single symbol",
)
def get_symbol(
    org_id: int,
    repository_id: int,
    symbol_id: int,
    user_id: int = Depends(get_org_membership),
    db: Session = Depends(get_db),
) -> SymbolDetail:
    _get_ready_repository(org_id, repository_id, db)

    row = db.execute(
        text("""
            SELECT
                id, symbol_name, qualified_name, symbol_type, file_path,
                start_line, end_line, language, is_async, is_exported,
                signature, docstring, parent_symbol_id
            FROM code_symbols
            WHERE id = :symbol_id
              AND repository_id = :repo_id
              AND organization_id = :org_id
        """),
        {"symbol_id": symbol_id, "repo_id": repository_id, "org_id": org_id},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return SymbolDetail(**dict(row._mapping))


# ── 3. Callers graph ──────────────────────────────────────────────────────────

@router.get(
    "/organizations/{org_id}/repositories/{repository_id}/symbols/{symbol_id}/callers",
    response_model=list[RelationshipEdge],
    summary="Get all symbols that call this symbol (incoming CALLS edges)",
)
def get_callers(
    org_id: int,
    repository_id: int,
    symbol_id: int,
    limit: int = Query(50, ge=1, le=200),
    user_id: int = Depends(get_org_membership),
    db: Session = Depends(get_db),
) -> list[RelationshipEdge]:
    _get_ready_repository(org_id, repository_id, db)

    rows = db.execute(
        text("""
            SELECT
                cr.source_symbol_id,
                src.symbol_name AS source_symbol_name,
                cr.source_file_path,
                cr.source_line,
                cr.target_symbol_id,
                tgt.symbol_name AS target_symbol_name,
                cr.target_file_path,
                cr.relationship_type,
                cr.confidence,
                cr.is_resolved
            FROM code_relationships cr
            LEFT JOIN code_symbols src ON cr.source_symbol_id = src.id
            LEFT JOIN code_symbols tgt ON cr.target_symbol_id = tgt.id
            WHERE
                cr.repository_id = :repo_id
                AND cr.organization_id = :org_id
                AND cr.target_symbol_id = :symbol_id
                AND cr.relationship_type = 'CALLS'
            ORDER BY cr.source_file_path, cr.source_line
            LIMIT :limit
        """),
        {"repo_id": repository_id, "org_id": org_id, "symbol_id": symbol_id, "limit": limit},
    ).fetchall()

    return [RelationshipEdge(**dict(r._mapping)) for r in rows]


# ── 4. Callees graph ──────────────────────────────────────────────────────────

@router.get(
    "/organizations/{org_id}/repositories/{repository_id}/symbols/{symbol_id}/callees",
    response_model=list[RelationshipEdge],
    summary="Get all symbols this symbol calls (outgoing CALLS edges)",
)
def get_callees(
    org_id: int,
    repository_id: int,
    symbol_id: int,
    limit: int = Query(50, ge=1, le=200),
    user_id: int = Depends(get_org_membership),
    db: Session = Depends(get_db),
) -> list[RelationshipEdge]:
    _get_ready_repository(org_id, repository_id, db)

    rows = db.execute(
        text("""
            SELECT
                cr.source_symbol_id,
                src.symbol_name AS source_symbol_name,
                cr.source_file_path,
                cr.source_line,
                cr.target_symbol_id,
                tgt.symbol_name AS target_symbol_name,
                cr.target_file_path,
                cr.relationship_type,
                cr.confidence,
                cr.is_resolved
            FROM code_relationships cr
            LEFT JOIN code_symbols src ON cr.source_symbol_id = src.id
            LEFT JOIN code_symbols tgt ON cr.target_symbol_id = tgt.id
            WHERE
                cr.repository_id = :repo_id
                AND cr.organization_id = :org_id
                AND cr.source_symbol_id = :symbol_id
                AND cr.relationship_type = 'CALLS'
            ORDER BY cr.target_symbol_name
            LIMIT :limit
        """),
        {"repo_id": repository_id, "org_id": org_id, "symbol_id": symbol_id, "limit": limit},
    ).fetchall()

    return [RelationshipEdge(**dict(r._mapping)) for r in rows]


# ── 5. References ─────────────────────────────────────────────────────────────

@router.get(
    "/organizations/{org_id}/repositories/{repository_id}/symbols/{symbol_id}/references",
    response_model=list[RelationshipEdge],
    summary="Get all IMPORTS or REFERENCES to this symbol",
)
def get_references(
    org_id: int,
    repository_id: int,
    symbol_id: int,
    relationship_types: Optional[str] = Query(
        None,
        description="Comma-separated types to include. Defaults to IMPORTS,REFERENCES,HANDLES",
    ),
    limit: int = Query(50, ge=1, le=200),
    user_id: int = Depends(get_org_membership),
    db: Session = Depends(get_db),
) -> list[RelationshipEdge]:
    _get_ready_repository(org_id, repository_id, db)

    types = (
        [t.strip() for t in relationship_types.split(",")]
        if relationship_types
        else ["IMPORTS", "REFERENCES", "HANDLES"]
    )

    rows = db.execute(
        text("""
            SELECT
                cr.source_symbol_id,
                src.symbol_name AS source_symbol_name,
                cr.source_file_path,
                cr.source_line,
                cr.target_symbol_id,
                tgt.symbol_name AS target_symbol_name,
                cr.target_file_path,
                cr.relationship_type,
                cr.confidence,
                cr.is_resolved
            FROM code_relationships cr
            LEFT JOIN code_symbols src ON cr.source_symbol_id = src.id
            LEFT JOIN code_symbols tgt ON cr.target_symbol_id = tgt.id
            WHERE
                cr.repository_id = :repo_id
                AND cr.organization_id = :org_id
                AND cr.target_symbol_id = :symbol_id
                AND cr.relationship_type = ANY(:types)
            ORDER BY cr.source_file_path
            LIMIT :limit
        """),
        {
            "repo_id": repository_id,
            "org_id": org_id,
            "symbol_id": symbol_id,
            "types": types,
            "limit": limit,
        },
    ).fetchall()

    return [RelationshipEdge(**dict(r._mapping)) for r in rows]


# ── 6. Route Catalog ──────────────────────────────────────────────────────────

@router.get(
    "/organizations/{org_id}/repositories/{repository_id}/routes",
    response_model=list[RouteEntry],
    summary="List all HTTP route symbols in the repository",
)
def list_routes(
    org_id: int,
    repository_id: int,
    file_path: Optional[str] = Query(None, description="Filter routes to a specific file"),
    user_id: int = Depends(get_org_membership),
    db: Session = Depends(get_db),
) -> list[RouteEntry]:
    _get_ready_repository(org_id, repository_id, db)

    params: dict = {
        "repo_id": repository_id,
        "org_id": org_id,
    }
    file_filter = "AND s.file_path = :file_path" if file_path else ""
    if file_path:
        params["file_path"] = file_path

    rows = db.execute(
        text(f"""
            SELECT
                s.symbol_name,
                s.qualified_name,
                s.file_path,
                s.start_line,
                s.signature,
                -- Resolve the handler via HANDLES relationship
                cr.target_symbol_id AS handler_symbol_id,
                handler.symbol_name AS handler_symbol_name,
                handler.file_path AS handler_file_path
            FROM code_symbols s
            LEFT JOIN code_relationships cr
                ON cr.source_symbol_id = s.id
                AND cr.relationship_type = 'HANDLES'
                AND cr.repository_id = s.repository_id
            LEFT JOIN code_symbols handler
                ON handler.id = cr.target_symbol_id
            WHERE
                s.repository_id = :repo_id
                AND s.organization_id = :org_id
                AND s.symbol_type = 'route'
                {file_filter}
            ORDER BY s.file_path, s.start_line
        """),
        params,
    ).fetchall()

    return [RouteEntry(**dict(r._mapping)) for r in rows]


# ── 7. File Structure ─────────────────────────────────────────────────────────

@router.get(
    "/organizations/{org_id}/repositories/{repository_id}/structure",
    response_model=list[FileEntry],
    summary="List all discovered files with index metadata",
)
def get_structure(
    org_id: int,
    repository_id: int,
    language: Optional[str] = Query(None),
    indexed_only: bool = Query(False),
    limit: int = Query(500, ge=1, le=2000),
    user_id: int = Depends(get_org_membership),
    db: Session = Depends(get_db),
) -> list[FileEntry]:
    _get_ready_repository(org_id, repository_id, db)

    params: dict = {
        "repo_id": repository_id,
        "org_id": org_id,
        "limit": limit,
    }
    lang_filter = "AND language = :language" if language else ""
    indexed_filter = "AND is_indexed = TRUE" if indexed_only else ""
    if language:
        params["language"] = language

    rows = db.execute(
        text(f"""
            SELECT
                path AS path,
                language,
                is_indexed,
                chunk_count,
                size_bytes
            FROM repository_files
            WHERE
                repository_id = :repo_id
                AND organization_id = :org_id
                {lang_filter}
                {indexed_filter}
            ORDER BY path
            LIMIT :limit
        """),
        params,
    ).fetchall()

    return [FileEntry(**dict(r._mapping)) for r in rows]


# ── 8. Symbol by name ─────────────────────────────────────────────────────────

@router.get(
    "/organizations/{org_id}/repositories/{repository_id}/symbols/by-name/{symbol_name}",
    response_model=list[SymbolDetail],
    summary="Find all symbols matching an exact name (may return multiple if overloaded)",
)
def get_symbols_by_name(
    org_id: int,
    repository_id: int,
    symbol_name: str,
    symbol_type: Optional[str] = Query(None),
    user_id: int = Depends(get_org_membership),
    db: Session = Depends(get_db),
) -> list[SymbolDetail]:
    _get_ready_repository(org_id, repository_id, db)

    params: dict = {
        "repo_id": repository_id,
        "org_id": org_id,
        "symbol_name": symbol_name,
    }
    type_filter = "AND symbol_type = :symbol_type" if symbol_type else ""
    if symbol_type:
        params["symbol_type"] = symbol_type

    rows = db.execute(
        text(f"""
            SELECT
                id, symbol_name, qualified_name, symbol_type, file_path,
                start_line, end_line, language, is_async, is_exported,
                signature, docstring, parent_symbol_id
            FROM code_symbols
            WHERE
                repository_id = :repo_id
                AND organization_id = :org_id
                AND (symbol_name = :symbol_name OR qualified_name = :symbol_name)
                {type_filter}
            ORDER BY file_path, start_line
        """),
        params,
    ).fetchall()

    return [SymbolDetail(**dict(r._mapping)) for r in rows]


# ── 9. Index Status ───────────────────────────────────────────────────────────

@router.get(
    "/organizations/{org_id}/repositories/{repository_id}/index-status",
    response_model=IndexStatus,
    summary="Get indexing health and relationship resolution statistics",
)
def get_index_status(
    org_id: int,
    repository_id: int,
    user_id: int = Depends(get_org_membership),
    db: Session = Depends(get_db),
) -> IndexStatus:
    repo = _get_ready_repository(org_id, repository_id, db, require_ready=False)

    # File counts
    file_row = db.execute(
        text("""
            SELECT
                COUNT(*) AS total_files,
                COUNT(*) FILTER (WHERE is_indexed = TRUE) AS indexed_files,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed_files
            FROM repository_files
            WHERE repository_id = :repo_id AND organization_id = :org_id
        """),
        {"repo_id": repository_id, "org_id": org_id},
    ).fetchone()

    # Symbol count
    sym_row = db.execute(
        text("""
            SELECT COUNT(*) AS total_symbols
            FROM code_symbols
            WHERE repository_id = :repo_id AND organization_id = :org_id
        """),
        {"repo_id": repository_id, "org_id": org_id},
    ).fetchone()

    # Relationship counts
    rel_row = db.execute(
        text("""
            SELECT
                COUNT(*) AS total_relationships,
                COUNT(*) FILTER (WHERE is_resolved = TRUE) AS resolved_relationships,
                COUNT(*) FILTER (WHERE is_resolved = FALSE) AS unresolved_relationships
            FROM code_relationships
            WHERE repository_id = :repo_id AND organization_id = :org_id
        """),
        {"repo_id": repository_id, "org_id": org_id},
    ).fetchone()

    fm = file_row._mapping if file_row else {}
    sm = sym_row._mapping if sym_row else {}
    rm = rel_row._mapping if rel_row else {}

    return IndexStatus(
        repository_id=repository_id,
        status=repo.status,
        total_files=fm.get("total_files", 0) or 0,
        indexed_files=fm.get("indexed_files", 0) or 0,
        failed_files=fm.get("failed_files", 0) or 0,
        total_symbols=sm.get("total_symbols", 0) or 0,
        resolved_relationships=rm.get("resolved_relationships", 0) or 0,
        unresolved_relationships=rm.get("unresolved_relationships", 0) or 0,
        total_relationships=rm.get("total_relationships", 0) or 0,
        last_synced_at=(
            repo.last_synced_at.isoformat() if repo.last_synced_at else None
        ),
    )
