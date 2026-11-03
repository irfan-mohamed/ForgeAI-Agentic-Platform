"""
repo_tools.py — Repository intelligence tool functions for Phase 3 agents.

Each function wraps one endpoint of the Repository Service internal API.
They are designed to be used as LangGraph tool nodes and can also be called
directly from the feature planner.

All functions:
  - Are synchronous (using httpx)
  - Return typed dicts or lists suitable for agent state
  - Propagate structured errors rather than raising bare exceptions
  - Use the REPOSITORY_SERVICE_URL setting

Tool catalogue (10 tools):
  1.  search_symbols        — FTS search over code symbols
  2.  get_symbol            — Single symbol detail by ID
  3.  get_symbol_by_name    — Resolve symbol by name (returns list)
  4.  get_callers           — Who calls this symbol?
  5.  get_callees           — What does this symbol call?
  6.  get_references        — What imports / references this symbol?
  7.  list_routes           — HTTP route catalog for the repo
  8.  get_file_structure    — Directory listing with index metadata
  9.  get_index_status      — Indexing health / stats
  10. semantic_search       — Vector similarity search via AI service retriever

Owned by: AI Service.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Default timeout for all repository service calls
_TIMEOUT = httpx.Timeout(30.0)


def _repo_get(path: str, params: dict | None = None) -> Any:
    """Synchronous GET against the repository service internal API."""
    url = f"{settings.REPOSITORY_SERVICE_URL}/api/v1{path}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning(
            "Repository service HTTP error",
            extra={"url": url, "status": e.response.status_code},
        )
        return {"error": str(e), "status_code": e.response.status_code}
    except Exception as e:
        logger.error("Repository service call failed", extra={"url": url, "error": str(e)})
        return {"error": str(e)}


# ── Tool 1: Symbol Search ─────────────────────────────────────────────────────

def search_symbols(
    org_id: int,
    repository_id: int,
    query: str,
    symbol_type: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """
    Full-text search over code symbols (functions, classes, routes, etc.)
    in a repository.

    Returns a list of symbol summaries with name, type, file path, and line range.

    Use this to find WHERE a function/class/route is defined.
    """
    params: dict = {"q": query, "limit": limit}
    if symbol_type:
        params["symbol_type"] = symbol_type
    if language:
        params["language"] = language

    result = _repo_get(
        f"/internal/organizations/{org_id}/repositories/{repository_id}/symbols/search",
        params,
    )
    return result if isinstance(result, list) else []


# ── Tool 2: Get Symbol by ID ─────────────────────────────────────────────────

def get_symbol(org_id: int, repository_id: int, symbol_id: int) -> dict:
    """
    Get full detail for a single code symbol by its database ID.

    Returns signature, docstring, line range, parent symbol, and more.
    Use this after search_symbols to get the complete definition.
    """
    return _repo_get(
        f"/internal/organizations/{org_id}/repositories/{repository_id}/symbols/{symbol_id}"
    )


# ── Tool 3: Get Symbol by Name ────────────────────────────────────────────────

def get_symbol_by_name(
    org_id: int,
    repository_id: int,
    symbol_name: str,
    symbol_type: Optional[str] = None,
) -> list[dict]:
    """
    Find all symbols matching an exact name.

    May return multiple results if a name is overloaded across files.
    Use this when you know the exact symbol name (e.g. 'UserService', 'login').
    """
    params = {}
    if symbol_type:
        params["symbol_type"] = symbol_type

    result = _repo_get(
        f"/internal/organizations/{org_id}/repositories/{repository_id}/symbols/by-name/{symbol_name}",
        params or None,
    )
    return result if isinstance(result, list) else []


# ── Tool 4: Get Callers ───────────────────────────────────────────────────────

def get_callers(
    org_id: int,
    repository_id: int,
    symbol_id: int,
    limit: int = 50,
) -> list[dict]:
    """
    Find all symbols that CALL a given symbol (incoming call edges).

    Use this to understand who uses a function — helpful for impact analysis
    before changing an API, or when tracing a bug to its callers.

    Example: "Who calls the `authenticate` function?"
    """
    result = _repo_get(
        f"/internal/organizations/{org_id}/repositories/{repository_id}/symbols/{symbol_id}/callers",
        {"limit": limit},
    )
    return result if isinstance(result, list) else []


# ── Tool 5: Get Callees ───────────────────────────────────────────────────────

def get_callees(
    org_id: int,
    repository_id: int,
    symbol_id: int,
    limit: int = 50,
) -> list[dict]:
    """
    Find all symbols that a given symbol CALLS (outgoing call edges).

    Use this to understand a function's dependencies — helpful for
    comprehending implementation details.

    Example: "What does `process_payment` call?"
    """
    result = _repo_get(
        f"/internal/organizations/{org_id}/repositories/{repository_id}/symbols/{symbol_id}/callees",
        {"limit": limit},
    )
    return result if isinstance(result, list) else []


# ── Tool 6: Get References ────────────────────────────────────────────────────

def get_references(
    org_id: int,
    repository_id: int,
    symbol_id: int,
    relationship_types: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """
    Find all IMPORTS, REFERENCES, and HANDLES relationships pointing to a symbol.

    Use this to trace all places that import or reference a module/class.

    Example: "Where is UserService imported?"
    """
    params: dict = {"limit": limit}
    if relationship_types:
        params["relationship_types"] = relationship_types

    result = _repo_get(
        f"/internal/organizations/{org_id}/repositories/{repository_id}/symbols/{symbol_id}/references",
        params,
    )
    return result if isinstance(result, list) else []


# ── Tool 7: List Routes ───────────────────────────────────────────────────────

def list_routes(
    org_id: int,
    repository_id: int,
    file_path: Optional[str] = None,
) -> list[dict]:
    """
    List all HTTP route symbols (endpoints) in the repository.

    Returns the route path/method, the file it's in, and the handler function
    if it was resolved.

    Use this to understand the API surface of the codebase.
    Example: "What API routes exist?" or "What handles POST /users?"
    """
    params = {}
    if file_path:
        params["file_path"] = file_path

    result = _repo_get(
        f"/internal/organizations/{org_id}/repositories/{repository_id}/routes",
        params or None,
    )
    return result if isinstance(result, list) else []


# ── Tool 8: Get File Structure ────────────────────────────────────────────────

def get_file_structure(
    org_id: int,
    repository_id: int,
    language: Optional[str] = None,
    indexed_only: bool = False,
    limit: int = 500,
) -> list[dict]:
    """
    Get the full file structure of the repository with index metadata.

    Returns each file's path, language, whether it's indexed, and chunk count.

    Use this to understand the project layout before planning changes.
    Example: "Show me all Python files" or "What's the directory structure?"
    """
    params: dict = {"limit": limit}
    if language:
        params["language"] = language
    if indexed_only:
        params["indexed_only"] = "true"

    result = _repo_get(
        f"/internal/organizations/{org_id}/repositories/{repository_id}/structure",
        params,
    )
    return result if isinstance(result, list) else []


# ── Tool 9: Get Index Status ──────────────────────────────────────────────────

def get_index_status(org_id: int, repository_id: int) -> dict:
    """
    Get the current indexing health and relationship resolution stats.

    Returns total/indexed/failed file counts, symbol counts, and relationship
    resolution percentages.

    Use this to check if the repository is fully indexed before searching.
    """
    return _repo_get(
        f"/internal/organizations/{org_id}/repositories/{repository_id}/index-status"
    )


# ── Tool 10: Semantic Code Search ─────────────────────────────────────────────

def semantic_search(
    query: str,
    org_id: int,
    repository_id: int,
    top_k: int = 8,
) -> list[dict]:
    """
    Vector similarity search over code chunks for conceptual/semantic questions.

    Use this for broad questions like "How does authentication work?"
    or "Where is rate limiting implemented?" — when you don't know
    the exact symbol name.

    Returns ranked code chunks with file path, line range, and content.
    """
    # Import lazily to avoid circular import at module level
    from app.services.hybrid_retriever import search as hybrid_search
    from app.services.intent_classifier import classify

    intent = classify(query)
    results = hybrid_search(
        query=query,
        org_id=org_id,
        repository_id=repository_id,
        intent=intent,
        top_k=top_k,
    )

    return [
        {
            "chunk_id": r.chunk_id,
            "file_path": r.file_path,
            "chunk_type": r.chunk_type,
            "start_line": r.start_line,
            "end_line": r.end_line,
            "language": r.language,
            "content": r.content[:2000],  # Cap per-chunk content for state size
            "score": r.score,
        }
        for r in results
    ]
