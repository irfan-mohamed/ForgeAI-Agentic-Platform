"""
runner.py — Benchmark execution engine for retrieval evaluation.

Calculates:
  - Recall@1, Recall@3, Recall@5, Recall@8
  - Mean Reciprocal Rank (MRR)
  - Latency: p50, p95, mean (in milliseconds)
  - Context Token Usage
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.evaluation.dataset import EvalTestCase
from app.services.retrieval.base import RetrievalResult, Retriever


@dataclass
class QueryEvalResult:
    case_id: str
    query: str
    category: str
    latency_ms: float
    reciprocal_rank: float
    hits_at_k: dict[int, bool]
    tokens: int
    matched_file: str | None = None
    matched_symbol: str | None = None


@dataclass
class BenchmarkReport:
    retriever_name: str
    total_queries: int
    mean_reciprocal_rank: float
    recall_at_k: dict[int, float]
    latency_p50_ms: float
    latency_p95_ms: float
    latency_mean_ms: float
    avg_tokens_per_query: float
    query_results: list[QueryEvalResult] = field(default_factory=list)

    def summary_table(self) -> str:
        """Renders an ASCII summary table of the benchmark."""
        lines = [
            f"=== Retrieval Benchmark Report: {self.retriever_name} ===",
            f"Queries Evaluated: {self.total_queries}",
            f"MRR (Mean Reciprocal Rank): {self.mean_reciprocal_rank:.4f}",
            "--- Recall Metrics ---",
        ]
        for k, score in sorted(self.recall_at_k.items()):
            lines.append(f"  Recall@{k}: {score * 100:.1f}%")
        lines.extend([
            "--- Performance & Cost ---",
            f"  Latency (mean): {self.latency_mean_ms:.2f} ms",
            f"  Latency (p50):  {self.latency_p50_ms:.2f} ms",
            f"  Latency (p95):  {self.latency_p95_ms:.2f} ms",
            f"  Avg Context Tokens: {self.avg_tokens_per_query:.0f} tokens",
            "=====================================================",
        ])
        return "\n".join(lines)


def _matches(candidate: RetrievalResult, case: EvalTestCase) -> bool:
    """Checks whether candidate satisfies the test case expectations."""
    cand_path = candidate.file_path.replace("\\", "/").lower()
    cand_content = candidate.content.lower()
    cand_symbol = (candidate.symbol_name or "").lower()
    cand_sig = (candidate.signature or "").lower()

    # File match
    for exp_file in case.expected_files:
        exp_clean = exp_file.replace("\\", "/").lower()
        if cand_path.endswith(exp_clean) or exp_clean.endswith(cand_path):
            return True

    # Symbol match
    for exp_sym in case.expected_symbols:
        exp_s = exp_sym.lower()
        if exp_s == cand_symbol or exp_s in cand_sig or exp_s in cand_content:
            return True

    # Route match
    for exp_route in case.expected_routes:
        if exp_route.lower() in cand_content or exp_route.lower() in cand_sig:
            return True

    return False


def evaluate_retriever(
    retriever: Retriever,
    test_cases: Sequence[EvalTestCase],
    org_id: int,
    repository_id: int,
    k_values: Sequence[int] = (1, 3, 5, 8),
) -> BenchmarkReport:
    """
    Executes all benchmark test queries against a Retriever and computes metrics.
    """
    max_k = max(k_values)
    query_results: list[QueryEvalResult] = []
    latencies: list[float] = []

    for case in test_cases:
        start_time = time.perf_counter()
        results = retriever.search(
            query=case.query,
            org_id=org_id,
            repository_id=repository_id,
            top_k=max_k,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        latencies.append(elapsed_ms)

        first_match_rank: int | None = None
        matched_file: str | None = None
        matched_symbol: str | None = None
        total_tokens = sum(len(r.content.split()) for r in results)

        for rank, res in enumerate(results, start=1):
            if _matches(res, case):
                if first_match_rank is None:
                    first_match_rank = rank
                    matched_file = res.file_path
                    matched_symbol = res.symbol_name or res.chunk_type

        rr = 1.0 / first_match_rank if first_match_rank is not None else 0.0
        hits: dict[int, bool] = {
            k: (first_match_rank is not None and first_match_rank <= k)
            for k in k_values
        }

        query_results.append(
            QueryEvalResult(
                case_id=case.id,
                query=case.query,
                category=case.category,
                latency_ms=elapsed_ms,
                reciprocal_rank=rr,
                hits_at_k=hits,
                tokens=total_tokens,
                matched_file=matched_file,
                matched_symbol=matched_symbol,
            )
        )

    # Compute aggregates
    total = len(test_cases)
    mrr = sum(q.reciprocal_rank for q in query_results) / total if total else 0.0
    recalls: dict[int, float] = {
        k: sum(1 for q in query_results if q.hits_at_k.get(k, False)) / total if total else 0.0
        for k in k_values
    }

    p50 = statistics.median(latencies) if latencies else 0.0
    latencies_sorted = sorted(latencies)
    p95_idx = int(len(latencies_sorted) * 0.95)
    p95 = latencies_sorted[p95_idx] if latencies else 0.0
    mean_lat = statistics.mean(latencies) if latencies else 0.0
    avg_tokens = (
        sum(q.tokens for q in query_results) / total if total else 0.0
    )

    retriever_name = getattr(retriever, "__class__", type(retriever)).__name__

    return BenchmarkReport(
        retriever_name=retriever_name,
        total_queries=total,
        mean_reciprocal_rank=mrr,
        recall_at_k=recalls,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        latency_mean_ms=mean_lat,
        avg_tokens_per_query=avg_tokens,
        query_results=query_results,
    )
