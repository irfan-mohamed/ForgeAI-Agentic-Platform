"""
evaluation package — Golden evaluation dataset and benchmark runner for ForgeAI retrieval.
"""
from app.evaluation.dataset import EVAL_DATASET, EvalTestCase
from app.evaluation.runner import BenchmarkReport, QueryEvalResult, evaluate_retriever

__all__ = [
    "EVAL_DATASET",
    "EvalTestCase",
    "BenchmarkReport",
    "QueryEvalResult",
    "evaluate_retriever",
]
