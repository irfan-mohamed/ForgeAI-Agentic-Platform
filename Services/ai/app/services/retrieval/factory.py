"""
factory.py — Strategy factory selecting the optimal Retriever per repository tier.

Decision matrix based on repository token size:
  - TINY (<= 60k tokens):
      AgenticRetriever (Repo map + targeted symbols + direct context, no vector overhead)
  - MEDIUM (60k–200k tokens):
      HybridRetriever without dense vectors (Lexical FTS + Trigrams + Symbol Graph + Reranker)
  - LARGE (> 200k tokens):
      HybridRetriever with dense vectors (Qdrant + Lexical + Symbol + Reranker)
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func, text

from app.db.database import db_session
from app.services.retrieval.agentic import AgenticRetriever
from app.services.retrieval.base import RepoTier, Retriever
from app.services.retrieval.hybrid import HybridRetriever
from app.services.retrieval.lexical import LexicalRetriever
from app.services.retrieval.symbol import SymbolRetriever
from app.services.retrieval.vector import VectorRetriever

logger = logging.getLogger(__name__)

# Token count thresholds
TIER_TINY_MAX_TOKENS = 60_000
TIER_MEDIUM_MAX_TOKENS = 200_000


def estimate_repo_tokens(org_id: int, repository_id: int) -> int:
    """
    Estimates total code tokens in a repository by querying repository_files.
    Rule of thumb: 1 token ≈ 4 characters/bytes.
    """
    try:
        with db_session() as db:
            result = db.execute(
                text("""
                    SELECT COALESCE(SUM(size_bytes), 0) AS total_bytes
                    FROM repository_files
                    WHERE organization_id = :org_id AND repository_id = :repo_id
                """),
                {"org_id": org_id, "repo_id": repository_id},
            ).fetchone()
            total_bytes = result[0] if result else 0
            return int(total_bytes / 4)
    except Exception as exc:
        logger.warning("Could not estimate repo tokens from repository_files", extra={"error": str(exc)})
        return 0


def detect_repo_tier(org_id: int, repository_id: int) -> RepoTier:
    """Detects repository tier based on token size."""
    estimated_tokens = estimate_repo_tokens(org_id, repository_id)

    if estimated_tokens <= TIER_TINY_MAX_TOKENS:
        return RepoTier.TINY
    if estimated_tokens <= TIER_MEDIUM_MAX_TOKENS:
        return RepoTier.MEDIUM
    return RepoTier.LARGE


def get_retriever_for_repo(
    org_id: int,
    repository_id: int,
    tier: Optional[RepoTier] = None,
    mode: Optional[str] = None,
) -> Retriever:
    """
    Factory function returning the configured or auto-detected Retriever for a repository.

    Args:
        org_id: Organization ID.
        repository_id: Repository ID.
        tier: Explicit RepoTier override (optional).
        mode: Explicit mode string: 'agentic', 'lexical', 'symbol', 'vector', 'hybrid'.
    """
    if mode == "agentic":
        return AgenticRetriever()
    if mode == "lexical":
        return LexicalRetriever()
    if mode == "symbol":
        return SymbolRetriever()
    if mode == "vector":
        return VectorRetriever()
    if mode == "hybrid":
        return HybridRetriever(use_vectors=True)

    detected_tier = tier or detect_repo_tier(org_id, repository_id)
    logger.info(
        "Selecting retriever strategy for repository",
        extra={"org_id": org_id, "repo_id": repository_id, "tier": detected_tier.value},
    )

    if detected_tier == RepoTier.TINY:
        return AgenticRetriever()
    if detected_tier == RepoTier.MEDIUM:
        # Lexical + Symbol + Reranker (no vector database load for medium repos)
        return HybridRetriever(use_vectors=False)
    # Large repositories get the full hybrid stack
    return HybridRetriever(use_vectors=True)
