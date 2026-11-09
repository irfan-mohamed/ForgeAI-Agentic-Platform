"""
reranker.py — Neural (fastembed BAAI/bge-reranker-base) and code-aware reranking.

Takes the candidate pool from lexical + vector retrieval (typically 20–50 chunks)
and reranks down to top_k (default 8).

Why reranking beats embedding model replacement:
  - Bi-encoders compress entire chunks into single fixed-size vectors (lossy).
  - Cross-encoders perform full cross-attention over (query, document) pairs.
  - BAAI/bge-reranker-base captures subtle interaction between code tokens and questions.
  - Code-aware scoring boosts exact symbol names and file paths directly.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Sequence

from app.core.config import settings

logger = logging.getLogger(__name__)

_cross_encoder = None
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def _extract_tokens(text: str) -> set[str]:
    """Extracts lowercase tokens from code or query."""
    return {t.lower() for t in _IDENTIFIER_PATTERN.findall(text) if len(t) >= 2}


def _get_cross_encoder():
    """Lazy loader for fastembed TextCrossEncoder."""
    global _cross_encoder
    if _cross_encoder is None:
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            logger.info("Loading cross-encoder reranker", extra={"model": settings.RERANKER_MODEL})
            _cross_encoder = TextCrossEncoder(model_name=settings.RERANKER_MODEL)
        except Exception as exc:
            logger.info("Fastembed cross-encoder unavailable — using deterministic code-aware reranker", extra={"error": str(exc)})
            _cross_encoder = False
    return _cross_encoder if _cross_encoder is not False else None


class CodeAwareReranker:
    """
    Combines neural cross-encoder scores (when available) with deterministic
    code heuristic boosts (symbol name match, file path match, multi-source agreement).
    """

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.RERANKER_MODEL

    def compute_code_heuristics_score(self, query: str, candidate: Any) -> float:
        """
        Calculates a deterministic boost score [0.0 - 1.0] based on code structure:
          - Exact symbol match in query: +0.40
          - File path / basename match: +0.25
          - Signature token overlap: +0.20
          - Multi-channel retrieval agreement (both semantic + symbol): +0.15
        """
        boost = 0.0
        query_lower = query.lower()
        query_tokens = _extract_tokens(query)

        symbol_name = getattr(candidate, "symbol_name", None)
        if symbol_name:
            sym_lower = symbol_name.lower()
            if sym_lower == query_lower.strip() or sym_lower in query_tokens:
                boost += 0.50
            elif sym_lower in query_lower:
                boost += 0.30

        file_path = getattr(candidate, "file_path", "")
        if file_path:
            fp_lower = file_path.lower()
            basename = fp_lower.split("/")[-1].split("\\")[-1]
            if basename in query_lower:
                boost += 0.25
            elif any(part in query_tokens for part in basename.split(".") if len(part) > 2):
                boost += 0.15

        signature = getattr(candidate, "signature", None)
        if signature:
            sig_tokens = _extract_tokens(signature)
            overlap = len(query_tokens & sig_tokens)
            if overlap > 0:
                boost += min(0.20, overlap * 0.05)

        # Multi-source agreement bonus: appeared in both vector search AND symbol FTS
        sources = getattr(candidate, "sources", [])
        if len(sources) > 1:
            boost += 0.15

        return boost

    def rerank(
        self,
        query: str,
        candidates: Sequence[Any],
        top_k: int = 8,
    ) -> list[Any]:
        """
        Reranks a list of candidate chunks.

        Args:
            query: The user's query string.
            candidates: Retrieved HybridResult or RetrievedChunk objects.
            top_k: Number of results to keep.

        Returns:
            Reranked list of top_k candidates with .rerank_score attached.
        """
        if not candidates:
            return []

        if len(candidates) <= 1:
            return list(candidates)

        encoder = _get_cross_encoder()
        scored_candidates: list[tuple[float, Any]] = []

        if encoder is not None:
            try:
                # Prepare document texts for neural cross-encoder
                doc_texts = [
                    f"{getattr(c, 'file_path', '')}\n{getattr(c, 'content', '')[:1000]}"
                    for c in candidates
                ]
                neural_scores = list(encoder.rerank(query, doc_texts))
                for c, n_score in zip(candidates, neural_scores):
                    code_boost = self.compute_code_heuristics_score(query, c)
                    # Blend neural score (0 to 1) with code boost
                    final_score = float(n_score) * 0.70 + code_boost * 0.30
                    c.rerank_score = final_score
                    scored_candidates.append((final_score, c))
            except Exception as exc:
                logger.warning("Neural reranking failed, falling back to heuristic reranking", extra={"error": str(exc)})
                scored_candidates = []

        if not scored_candidates:
            # Deterministic code-aware fallback
            max_rrf = max((getattr(c, "rrf_score", getattr(c, "score", 1.0)) for c in candidates), default=1.0)
            max_rrf = max_rrf if max_rrf > 0 else 1.0

            for c in candidates:
                base_score = getattr(c, "rrf_score", getattr(c, "score", 0.0)) / max_rrf
                code_boost = self.compute_code_heuristics_score(query, c)
                final_score = base_score * 0.45 + code_boost * 0.55
                c.rerank_score = final_score
                scored_candidates.append((final_score, c))

        # Sort descending by score
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored_candidates[:top_k]]


# Module singleton
_reranker_instance = CodeAwareReranker()


def rerank(query: str, candidates: Sequence[Any], top_k: int = 8) -> list[Any]:
    """Module-level entrypoint for reranking."""
    return _reranker_instance.rerank(query, candidates, top_k=top_k)
