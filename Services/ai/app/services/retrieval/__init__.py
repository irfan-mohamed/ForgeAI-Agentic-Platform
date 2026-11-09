"""
retrieval package — Pluggable retrieval architectures for ForgeAI.
"""
from app.services.retrieval.agentic import AgenticRetriever
from app.services.retrieval.base import RepoTier, RetrievalResult, Retriever
from app.services.retrieval.factory import (
    TIER_MEDIUM_MAX_TOKENS,
    TIER_TINY_MAX_TOKENS,
    detect_repo_tier,
    estimate_repo_tokens,
    get_retriever_for_repo,
)
from app.services.retrieval.hybrid import HybridRetriever
from app.services.retrieval.lexical import LexicalRetriever
from app.services.retrieval.symbol import SymbolRetriever
from app.services.retrieval.vector import VectorRetriever

__all__ = [
    "Retriever",
    "RetrievalResult",
    "RepoTier",
    "AgenticRetriever",
    "LexicalRetriever",
    "SymbolRetriever",
    "VectorRetriever",
    "HybridRetriever",
    "get_retriever_for_repo",
    "detect_repo_tier",
    "estimate_repo_tokens",
    "TIER_TINY_MAX_TOKENS",
    "TIER_MEDIUM_MAX_TOKENS",
]
