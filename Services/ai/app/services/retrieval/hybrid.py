"""
hybrid.py — Pluggable HybridRetriever combining vector, lexical, and symbol channels with RRF and reranker.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.core.config import settings
from app.services.hybrid_retriever import reciprocal_rank_fusion
from app.services.reranker import rerank
from app.services.retrieval.base import RetrievalResult, Retriever
from app.services.retrieval.lexical import LexicalRetriever
from app.services.retrieval.symbol import SymbolRetriever
from app.services.retrieval.vector import VectorRetriever

logger = logging.getLogger(__name__)


class HybridRetriever(Retriever):
    """
    Multimodal code retriever:
      - Runs Lexical (Postgres FTS + Trigram) and Vector (Qdrant + BGE) searches in parallel.
      - Fuses channels with Reciprocal Rank Fusion (RRF).
      - Reranks top candidates with neural or code-aware cross-encoder.
    """

    def __init__(self, use_vectors: bool = True, use_reranker: bool = True):
        self.use_vectors = use_vectors
        self.use_reranker = use_reranker
        self._lexical = LexicalRetriever()
        self._symbol = SymbolRetriever()
        self._vector = VectorRetriever() if use_vectors else None

    def search(
        self,
        query: str,
        org_id: int,
        repository_id: int,
        top_k: int = 8,
        **kwargs: Any,
    ) -> list[RetrievalResult]:
        pool_size = max(top_k * 3, 20)
        channel_results: list[list[RetrievalResult]] = []

        # Parallel dispatch across enabled channels
        tasks = [("lexical", self._lexical)]
        if self._vector:
            tasks.append(("vector", self._vector))

        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            future_to_name = {
                executor.submit(backend.search, query, org_id, repository_id, pool_size): name
                for name, backend in tasks
            }
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    res = future.result()
                    channel_results.append(res)
                except Exception as exc:
                    logger.warning("Channel search failed in HybridRetriever", extra={"channel": name, "error": str(exc)})

        # Build ranked lists for RRF
        ranked_lists = [
            [(item.chunk_id, item.score) for item in channel_list]
            for channel_list in channel_results
        ]
        rrf_scores = reciprocal_rank_fusion(*ranked_lists) if ranked_lists else {}

        # Merge and deduplicate
        merged_map: dict[str, RetrievalResult] = {}
        for channel_list in channel_results:
            for item in channel_list:
                cid = item.chunk_id
                if cid in merged_map:
                    # Append source
                    for s in item.sources:
                        if s not in merged_map[cid].sources:
                            merged_map[cid].sources.append(s)
                    merged_map[cid].score = max(merged_map[cid].score, rrf_scores.get(cid, item.score))
                else:
                    item.score = rrf_scores.get(cid, item.score)
                    merged_map[cid] = item

        candidates = sorted(merged_map.values(), key=lambda r: r.score, reverse=True)
        candidate_pool = candidates[:getattr(settings, "RAG_CANDIDATE_POOL_SIZE", 30)]

        # Rerank if enabled
        if self.use_reranker and getattr(settings, "RAG_RERANK_ENABLED", True) and candidate_pool:
            try:
                return rerank(query=query, candidates=candidate_pool, top_k=top_k)
            except Exception as exc:
                logger.warning("Reranking failed in HybridRetriever", extra={"error": str(exc)})

        return candidate_pool[:top_k]
