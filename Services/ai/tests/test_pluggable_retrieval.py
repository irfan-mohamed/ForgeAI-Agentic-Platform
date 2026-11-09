"""
test_pluggable_retrieval.py — Tests for the pluggable retrieval backends and factory.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from app.services.retrieval import (
    AgenticRetriever,
    HybridRetriever,
    LexicalRetriever,
    RepoTier,
    RetrievalResult,
    Retriever,
    SymbolRetriever,
    VectorRetriever,
    detect_repo_tier,
    estimate_repo_tokens,
    get_retriever_for_repo,
)


def test_retriever_protocol_compliance():
    """Verify that all retrieval classes conform to the Retriever protocol."""
    assert isinstance(LexicalRetriever(), Retriever)
    assert isinstance(SymbolRetriever(), Retriever)
    assert isinstance(VectorRetriever(), Retriever)
    assert isinstance(AgenticRetriever(), Retriever)
    assert isinstance(HybridRetriever(use_vectors=False), Retriever)


def test_factory_explicit_mode():
    """Verify get_retriever_for_repo with explicit mode selection."""
    assert isinstance(get_retriever_for_repo(1, 1, mode="agentic"), AgenticRetriever)
    assert isinstance(get_retriever_for_repo(1, 1, mode="lexical"), LexicalRetriever)
    assert isinstance(get_retriever_for_repo(1, 1, mode="symbol"), SymbolRetriever)
    assert isinstance(get_retriever_for_repo(1, 1, mode="vector"), VectorRetriever)

    h_retriever = get_retriever_for_repo(1, 1, mode="hybrid")
    assert isinstance(h_retriever, HybridRetriever)
    assert h_retriever.use_vectors is True


def test_factory_tier_selection():
    """Verify strategy chosen per repository tier."""
    r_tiny = get_retriever_for_repo(1, 1, tier=RepoTier.TINY)
    assert isinstance(r_tiny, AgenticRetriever)

    r_med = get_retriever_for_repo(1, 1, tier=RepoTier.MEDIUM)
    assert isinstance(r_med, HybridRetriever)
    assert r_med.use_vectors is False  # Saves vector DB overhead for medium tier

    r_large = get_retriever_for_repo(1, 1, tier=RepoTier.LARGE)
    assert isinstance(r_large, HybridRetriever)
    assert r_large.use_vectors is True


def test_detect_repo_tier_thresholds():
    """Verify token threshold boundaries."""
    with patch("app.services.retrieval.factory.estimate_repo_tokens") as mock_est:
        mock_est.return_value = 40_000
        assert detect_repo_tier(1, 1) == RepoTier.TINY

        mock_est.return_value = 100_000
        assert detect_repo_tier(1, 1) == RepoTier.MEDIUM

        mock_est.return_value = 350_000
        assert detect_repo_tier(1, 1) == RepoTier.LARGE


def test_agentic_retriever_includes_repo_map():
    """Verify AgenticRetriever pulls repo map into context."""
    with patch("app.services.retrieval.agentic.get_repo_map") as mock_get_map:
        mock_get_map.return_value = {
            "repository_id": 1,
            "raw_markdown": "# Repository Map: Acme\n## Routes\n- GET /ping",
        }
        retriever = AgenticRetriever()
        results = retriever.search("where is ping?", org_id=1, repository_id=1)

        assert len(results) >= 1
        assert any(r.chunk_type == "repo_map" for r in results)
        assert results[0].content.startswith("# Repository Map: Acme")
