"""
hybrid_retriever.py — Parallel semantic + lexical code search with RRF fusion.

Combines two complementary search channels:
  1. Semantic search  — existing Qdrant vector search (finds behaviorally
                         similar code even when names differ)
  2. Symbol search    — PostgreSQL FTS on code_symbols (finds exact or
                         lexically similar function/class/method names)

Results from both channels are merged using Reciprocal Rank Fusion (RRF),
which rewards chunks that appear in multiple channels without over-weighting
high scores from a single channel.

This is intentionally simple and synchronous for Phase 1.
Phase 3 will replace the core search call with the LangGraph agent tools.

Thread safety: all operations are stateless; safe to call from multiple threads.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from sqlalchemy import text

from app.core.config import settings
from app.db.database import db_session
from app.services.intent_classifier import (
    Intent,
    DEFINITION_SEARCH,
    REFERENCE_SEARCH,
    CALLER_SEARCH,
    CALLEE_SEARCH,
    ROUTE_SEARCH,
    SEMANTIC_SEARCH,
    classify,
)

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class HybridResult:
    """A single merged result from the hybrid search."""
    chunk_id: str           # Qdrant point ID or "sym:<symbol_id>"
    file_path: str
    content: str
    start_line: int
    end_line: int
    language: str
    chunk_type: str         # function | class | method | route | raw | symbol
    rrf_score: float        # Reciprocal Rank Fusion score (higher = more relevant)
    sources: list[str]      # ["semantic", "symbol"] — which channels returned it
    # Symbol-specific fields (only set for lexical/symbol results)
    symbol_name: str | None = None
    symbol_type: str | None = None
    signature: str | None = None


# ── RRF implementation ────────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    *ranked_lists: list[tuple[str, float]],
    k: int = 60,
) -> dict[str, float]:
    """
    Merge multiple ranked result lists using Reciprocal Rank Fusion.

    Args:
        *ranked_lists: Each list is [(id, score), ...] ordered best-first.
        k:             RRF constant (60 is the standard default).

    Returns:
        Dict mapping id → combined RRF score. Higher is better.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (item_id, _) in enumerate(ranked, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


# ── Symbol search (PostgreSQL FTS) ────────────────────────────────────────────

def _search_symbols_lexical(
    query: str,
    org_id: int,
    repository_id: int,
    limit: int = 20,
) -> list[tuple[str, float, dict]]:
    """
    Searches code_symbols using PostgreSQL full-text search.

    Returns: [(synthetic_id, rank_score, symbol_row_dict), ...]
    """
    results = []
    try:
        with db_session() as db:
            rows = db.execute(
                text("""
                    SELECT
                        id,
                        symbol_name,
                        qualified_name,
                        symbol_type,
                        file_path,
                        start_line,
                        end_line,
                        signature,
                        docstring,
                        language,
                        ts_rank(search_vector, plainto_tsquery('english', :query)) AS rank
                    FROM code_symbols
                    WHERE
                        organization_id = :org_id
                        AND repository_id = :repo_id
                        AND search_vector @@ plainto_tsquery('english', :query)
                    ORDER BY rank DESC
                    LIMIT :limit
                """),
                {
                    "query": query,
                    "org_id": org_id,
                    "repo_id": repository_id,
                    "limit": limit,
                },
            ).fetchall()

        for row in rows:
            m = row._mapping
            synthetic_id = f"sym:{m['id']}"
            results.append((synthetic_id, float(m["rank"]), dict(m)))

    except Exception as exc:
        logger.warning(
            "Symbol FTS search failed",
            extra={"org_id": org_id, "repository_id": repository_id, "error": str(exc)},
        )

    return results


def _symbol_to_hybrid_result(sym_id: str, sym: dict, rrf_score: float) -> HybridResult:
    """Convert a code_symbols row into a HybridResult."""
    # Build a content snippet for context assembly
    content_parts = []
    if sym.get("signature"):
        content_parts.append(sym["signature"])
    if sym.get("docstring"):
        content_parts.append(f'"""{sym["docstring"]}"""')
    content = "\n".join(content_parts) or sym.get("symbol_name", "")

    return HybridResult(
        chunk_id=sym_id,
        file_path=sym.get("file_path", ""),
        content=content,
        start_line=sym.get("start_line") or 0,
        end_line=sym.get("end_line") or 0,
        language=sym.get("language") or "",
        chunk_type=sym.get("symbol_type") or "symbol",
        rrf_score=rrf_score,
        sources=["symbol"],
        symbol_name=sym.get("symbol_name"),
        symbol_type=sym.get("symbol_type"),
        signature=sym.get("signature"),
    )


def _chunk_to_hybrid_result(chunk: RetrievedChunk, rrf_score: float) -> HybridResult:
    """Convert a Qdrant RetrievedChunk into a HybridResult."""
    return HybridResult(
        chunk_id=chunk.chunk_id,
        file_path=chunk.file_path,
        content=chunk.content,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        language=chunk.language,
        chunk_type=chunk.chunk_type,
        rrf_score=rrf_score,
        sources=["semantic"],
    )


# ── Strategy selection ────────────────────────────────────────────────────────

def _weights_for_intent(intent: Intent) -> tuple[float, float]:
    """
    Returns (semantic_weight, symbol_weight) for a given intent.

    Intent                → channel weights
    DEFINITION_SEARCH     → boost symbol (exact name match)
    CALLER/CALLEE_SEARCH  → boost symbol (need precise symbol IDs)
    ROUTE_SEARCH          → boost symbol (route symbols)
    REFERENCE_SEARCH      → balanced
    SEMANTIC_SEARCH       → boost semantic
    """
    weights = {
        DEFINITION_SEARCH: (0.4, 0.6),
        CALLER_SEARCH:     (0.3, 0.7),
        CALLEE_SEARCH:     (0.3, 0.7),
        ROUTE_SEARCH:      (0.2, 0.8),
        REFERENCE_SEARCH:  (0.5, 0.5),
        SEMANTIC_SEARCH:   (0.7, 0.3),
    }
    return weights.get(intent.intent, (0.6, 0.4))


# ── Public search API ─────────────────────────────────────────────────────────

def search(
    query: str,
    org_id: int,
    repository_id: int,
    intent: Intent | None = None,
    top_k: int | None = None,
) -> list[HybridResult]:
    """
    Run parallel semantic + symbol search and merge results with RRF.

    Args:
        query:         The user's natural language question.
        org_id:        Verified organization ID.
        repository_id: Verified repository ID.
        intent:        Pre-classified intent; if None, runs SEMANTIC_SEARCH.
        top_k:         Number of results to return (default: RAG_TOP_K setting).

    Returns:
        Merged, deduplicated list sorted by RRF score descending.
    """
    if intent is None:
        intent = classify(query)

    # Lazy import — avoids pulling in qdrant_client at module level
    # (keeps reciprocal_rank_fusion testable without infrastructure)
    from app.services.retriever import RetrievedChunk, search_repository

    top_k = top_k or settings.RAG_TOP_K
    sem_k = max(top_k, 10)   # Fetch more from semantic to give RRF room to work
    lex_k = max(top_k, 15)

    semantic_weight, symbol_weight = _weights_for_intent(intent)

    # Run both searches in parallel threads (both are blocking I/O)
    semantic_chunks: list[RetrievedChunk] = []
    symbol_rows: list[tuple[str, float, dict]] = []

    with ThreadPoolExecutor(max_workers=2) as ex:
        sem_future = ex.submit(search_repository, query, org_id, repository_id, sem_k)
        lex_future = ex.submit(_search_symbols_lexical, query, org_id, repository_id, lex_k)

        for future in as_completed([sem_future, lex_future]):
            try:
                result = future.result()
                if future is sem_future:
                    semantic_chunks = result
                else:
                    symbol_rows = result
            except Exception as exc:
                logger.warning(
                    "One search channel failed",
                    extra={"error": str(exc)},
                )

    logger.info(
        "Hybrid search channels complete",
        extra={
            "org_id": org_id,
            "repository_id": repository_id,
            "intent": intent.intent,
            "semantic_results": len(semantic_chunks),
            "symbol_results": len(symbol_rows),
        },
    )

    # Build per-channel ranked lists for RRF
    sem_ranked = [(c.chunk_id, c.score) for c in semantic_chunks]
    sym_ranked = [(sym_id, rank) for sym_id, rank, _ in symbol_rows]

    # Apply RRF
    rrf_scores = reciprocal_rank_fusion(sem_ranked, sym_ranked)

    # Build result objects and tag sources
    result_map: dict[str, HybridResult] = {}

    for chunk in semantic_chunks:
        r = _chunk_to_hybrid_result(chunk, rrf_scores.get(chunk.chunk_id, 0.0))
        result_map[chunk.chunk_id] = r

    for sym_id, _, sym_data in symbol_rows:
        if sym_id in result_map:
            # Item appeared in both — tag both sources, keep best score
            result_map[sym_id].sources.append("symbol")
            result_map[sym_id].rrf_score = rrf_scores.get(sym_id, 0.0)
        else:
            r = _symbol_to_hybrid_result(sym_id, sym_data, rrf_scores.get(sym_id, 0.0))
            result_map[sym_id] = r

    # Sort by RRF score, return top_k
    sorted_results = sorted(result_map.values(), key=lambda r: r.rrf_score, reverse=True)
    return sorted_results[:top_k]
