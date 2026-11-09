"""
agentic.py — Vectorless AgenticRetriever using Repo Map + Symbol Lookups.

Designed for tiny/small repositories (< 60k tokens) or vectorless mode:
  - Fetches repository map (file tree, routes, key components, tests, docs).
  - Searches relevant symbols without vector database overhead.
  - Returns compact, high-signal structural context.
"""
from __future__ import annotations

import logging
from typing import Any

from app.services.repo_tools import get_repo_map
from app.services.retrieval.base import RetrievalResult, Retriever
from app.services.retrieval.symbol import SymbolRetriever

logger = logging.getLogger(__name__)


class AgenticRetriever(Retriever):
    """
    Vectorless retriever: leverages the repo map and structural symbol graph
    to provide comprehensive context for smaller repositories without embedding cost.
    """

    def __init__(self):
        self._symbol_retriever = SymbolRetriever()

    def search(
        self,
        query: str,
        org_id: int,
        repository_id: int,
        top_k: int = 8,
        **kwargs: Any,
    ) -> list[RetrievalResult]:
        results: list[RetrievalResult] = []

        # 1. Fetch Repository Map
        try:
            repo_map = get_repo_map(org_id, repository_id)
            if repo_map and repo_map.get("raw_markdown"):
                raw_md = repo_map["raw_markdown"]
                results.append(
                    RetrievalResult(
                        chunk_id=f"map:{repository_id}",
                        file_path="REPO_MAP.md",
                        content=raw_md,
                        start_line=1,
                        end_line=len(raw_md.splitlines()),
                        language="markdown",
                        chunk_type="repo_map",
                        score=1.5,
                        sources=["agentic"],
                    )
                )
        except Exception as exc:
            logger.warning("AgenticRetriever failed to get repo map", extra={"error": str(exc)})

        # 2. Add targeted symbol search results
        sym_results = self._symbol_retriever.search(
            query=query,
            org_id=org_id,
            repository_id=repository_id,
            top_k=max(top_k - len(results), 2),
        )
        for s in sym_results:
            s.sources = ["agentic", "symbol"]
            results.append(s)

        return results[:top_k]
