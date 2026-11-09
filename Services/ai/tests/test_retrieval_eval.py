"""
test_retrieval_eval.py — Tests for the retrieval evaluation set and benchmark runner.
"""
from __future__ import annotations

import pytest

from app.evaluation.dataset import EVAL_DATASET, EvalTestCase
from app.evaluation.runner import evaluate_retriever
from app.services.retrieval.base import RetrievalResult, Retriever


class MockRetriever:
    """Mock retriever returning predictable results for eval testing."""

    def __init__(self, hit_rate: float = 1.0):
        self.hit_rate = hit_rate

    def search(self, query: str, org_id: int, repository_id: int, top_k: int = 8, **kwargs):
        if "User model" in query:
            return [
                RetrievalResult(
                    chunk_id="chunk-1",
                    file_path="app/models/user.py",
                    content="class User(Base): pass",
                    start_line=1,
                    end_line=10,
                    language="python",
                    chunk_type="class",
                    score=0.95,
                    sources=["symbol"],
                    symbol_name="User",
                )
            ]
        elif "POST /conversations" in query:
            return [
                RetrievalResult(
                    chunk_id="chunk-2",
                    file_path="app/api/routes/conversations.py",
                    content="@router.post('/organizations/{org_id}/conversations')\ndef create_conversation(): pass",
                    start_line=80,
                    end_line=100,
                    language="python",
                    chunk_type="route",
                    score=0.90,
                    sources=["symbol"],
                    symbol_name="create_conversation",
                )
            ]
        # Generic miss
        return [
            RetrievalResult(
                chunk_id="chunk-3",
                file_path="app/utils/other.py",
                content="def helper(): pass",
                start_line=1,
                end_line=5,
                language="python",
                chunk_type="function",
                score=0.3,
                sources=["lexical"],
                symbol_name="helper",
            )
        ]


def test_eval_dataset_structure():
    """Verify golden dataset contains required queries across all categories."""
    assert len(EVAL_DATASET) >= 30
    categories = {case.category for case in EVAL_DATASET}
    assert "definition" in categories
    assert "route" in categories
    assert "caller" in categories
    assert "semantic" in categories
    assert "multi_file" in categories

    for case in EVAL_DATASET:
        assert case.id
        assert case.query
        assert case.category
        assert case.expected_files or case.expected_symbols or case.expected_routes


def test_evaluate_retriever_computes_metrics():
    """Verify benchmark runner accurately computes Recall@k, MRR, latency, and tokens."""
    retriever = MockRetriever()
    cases = EVAL_DATASET[:6]  # Test subset of cases

    report = evaluate_retriever(
        retriever=retriever,
        test_cases=cases,
        org_id=1,
        repository_id=1,
        k_values=[1, 3, 5, 8],
    )

    assert report.total_queries == 6
    assert 0.0 <= report.mean_reciprocal_rank <= 1.0
    assert 1 in report.recall_at_k
    assert 8 in report.recall_at_k
    assert report.latency_mean_ms >= 0.0
    assert report.avg_tokens_per_query >= 0

    table = report.summary_table()
    assert "Retrieval Benchmark Report" in table
    assert "MRR" in table
    assert "Recall@8" in table
