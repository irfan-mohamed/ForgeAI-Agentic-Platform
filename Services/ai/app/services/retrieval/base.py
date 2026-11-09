"""
base.py — Core protocols and data classes for pluggable retrieval.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class RepoTier(str, enum.Enum):
    """Repository sizing tiers for retrieval strategy selection."""
    TINY = "tiny"        # <= 60k tokens: agentic / repo-map retrieval, no dense embeddings needed
    MEDIUM = "medium"    # 60k - 200k tokens: lexical FTS + symbol graph + optional vectors
    LARGE = "large"      # > 200k tokens: hybrid (dense vector + lexical FTS + symbol graph) + reranker


@dataclass
class RetrievalResult:
    """Unified retrieval result across all backends."""
    chunk_id: str
    file_path: str
    content: str
    start_line: int
    end_line: int
    language: str
    chunk_type: str         # function | class | method | route | raw | symbol | repo_map
    score: float            # Ranking score (higher is better)
    sources: list[str] = field(default_factory=list)  # ["vector"], ["lexical"], ["symbol"], ["agentic"]
    symbol_name: str | None = None
    symbol_type: str | None = None
    signature: str | None = None
    rerank_score: float | None = None

    @property
    def rrf_score(self) -> float:
        return self.score


@runtime_checkable
class Retriever(Protocol):
    """Pluggable Retriever interface."""

    def search(
        self,
        query: str,
        org_id: int,
        repository_id: int,
        top_k: int = 8,
        **kwargs: Any,
    ) -> list[RetrievalResult]:
        """Search repository for relevant code passages or symbols."""
        ...
