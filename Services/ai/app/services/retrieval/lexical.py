"""
lexical.py — LexicalRetriever backed by PostgreSQL FTS (simple config) + Trigram + Code Splitting.
"""
from __future__ import annotations

import logging
from typing import Any

from app.db.database import db_session
from app.services.hybrid_retriever import _search_symbols_lexical
from app.services.retrieval.base import RetrievalResult, Retriever

logger = logging.getLogger(__name__)


class LexicalRetriever(Retriever):
    """
    Retrieves code symbols and occurrences using PostgreSQL full-text search with
    'simple' configuration, camelCase/snake_case tokenization, and exact/prefix boosts.
    """

    def search(
        self,
        query: str,
        org_id: int,
        repository_id: int,
        top_k: int = 8,
        **kwargs: Any,
    ) -> list[RetrievalResult]:
        symbol_rows = _search_symbols_lexical(
            query=query,
            org_id=org_id,
            repository_id=repository_id,
            limit=top_k * 2,
        )

        results: list[RetrievalResult] = []
        for sym_id, rank, sym in symbol_rows:
            content_parts = []
            if sym.get("signature"):
                content_parts.append(sym["signature"])
            if sym.get("docstring"):
                content_parts.append(f'"""{sym["docstring"]}"""')
            content = "\n".join(content_parts) or sym.get("symbol_name", "")

            results.append(
                RetrievalResult(
                    chunk_id=sym_id,
                    file_path=sym.get("file_path", ""),
                    content=content,
                    start_line=sym.get("start_line", 0) or 0,
                    end_line=sym.get("end_line", 0) or 0,
                    language=sym.get("language") or "",
                    chunk_type=sym.get("symbol_type") or "symbol",
                    score=rank,
                    sources=["lexical"],
                    symbol_name=sym.get("symbol_name"),
                    symbol_type=sym.get("symbol_type"),
                    signature=sym.get("signature"),
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
