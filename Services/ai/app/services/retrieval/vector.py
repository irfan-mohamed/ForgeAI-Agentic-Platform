"""
vector.py — VectorRetriever backed by Qdrant dense vector search with BGE query instruction.
"""
from __future__ import annotations

import logging
from typing import Any

from app.services.retrieval.base import RetrievalResult, Retriever
from app.services.retriever import search_repository

logger = logging.getLogger(__name__)


class VectorRetriever(Retriever):
    """
    Dense semantic search using fastembed + Qdrant collection.
    Applies BGE query instruction prefix automatically.
    """

    def search(
        self,
        query: str,
        org_id: int,
        repository_id: int,
        top_k: int = 8,
        **kwargs: Any,
    ) -> list[RetrievalResult]:
        try:
            chunks = search_repository(
                query=query,
                org_id=org_id,
                repository_id=repository_id,
                top_k=top_k,
            )
            return [
                RetrievalResult(
                    chunk_id=c.chunk_id,
                    file_path=c.file_path,
                    content=c.content,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    language=c.language,
                    chunk_type=c.chunk_type,
                    score=c.score,
                    sources=["vector"],
                )
                for c in chunks
            ]
        except Exception as exc:
            logger.warning("VectorRetriever search failed", extra={"error": str(exc)})
            return []
