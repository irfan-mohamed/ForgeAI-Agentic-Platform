"""
test_reranker.py — Unit tests for the CodeAwareReranker.
"""
from __future__ import annotations

import pytest

from app.services.reranker import CodeAwareReranker, rerank
from app.services.retrieval.base import RetrievalResult


def _make_candidate(
    cid: str,
    file_path: str,
    content: str,
    symbol_name: str | None = None,
    signature: str | None = None,
    sources: list[str] | None = None,
    score: float = 0.5,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=cid,
        file_path=file_path,
        content=content,
        start_line=1,
        end_line=20,
        language="python",
        chunk_type="function",
        score=score,
        sources=sources or ["semantic"],
        symbol_name=symbol_name,
        signature=signature,
    )


def test_reranker_exact_symbol_boost():
    """Verify that candidate with exact symbol match is boosted to the top."""
    reranker = CodeAwareReranker()

    c1 = _make_candidate("1", "app/utils.py", "def helper(): pass", symbol_name="helper", score=0.9)
    c2 = _make_candidate("2", "app/auth.py", "def authenticate_user(): pass", symbol_name="authenticate_user", score=0.6)

    # Query specifically asks for authenticate_user
    reranked = reranker.rerank(
        query="where is authenticate_user defined?",
        candidates=[c1, c2],
        top_k=2,
    )

    # c2 should jump ahead of c1 due to exact symbol boost
    assert reranked[0].chunk_id == "2"
    assert reranked[0].symbol_name == "authenticate_user"


def test_reranker_file_path_boost():
    """Verify candidate from referenced file is boosted."""
    reranker = CodeAwareReranker()

    c1 = _make_candidate("1", "app/routes/billing.py", "code block", score=0.8)
    c2 = _make_candidate("2", "app/routes/users.py", "code block", score=0.7)

    reranked = reranker.rerank(
        query="check the handler in users.py",
        candidates=[c1, c2],
        top_k=2,
    )

    assert reranked[0].chunk_id == "2"
    assert "users.py" in reranked[0].file_path


def test_reranker_multi_source_bonus():
    """Verify candidate appearing in both semantic and symbol channels gets agreement boost."""
    reranker = CodeAwareReranker()

    c1 = _make_candidate("1", "app/service.py", "some code", sources=["semantic"], score=0.5)
    c2 = _make_candidate("2", "app/service.py", "some code", sources=["semantic", "symbol"], score=0.5)

    reranked = reranker.rerank(
        query="how does service work?",
        candidates=[c1, c2],
        top_k=2,
    )

    assert reranked[0].chunk_id == "2"
    assert len(reranked[0].sources) == 2


def test_rerank_top_k_limiting():
    """Verify top_k bounds."""
    candidates = [_make_candidate(str(i), f"file_{i}.py", f"content {i}") for i in range(15)]
    results = rerank("test query", candidates, top_k=5)
    assert len(results) == 5
