"""
Offline evaluation module for ScholarRAG.

This module provides deterministic offline evaluation for:
- Retrieval quality metrics
- Citation coverage validation
- Version-aware retrieval checks
- Machine-readable JSON reports

Usage:
    python -m tests.evaluation.runner
    python -m tests.evaluation.runner --help
"""

from tests.evaluation.dataset import EvalDataset, EvalQuery, load_dataset, save_dataset
from tests.evaluation.metrics import (
    EvaluationMetrics,
    QueryResult,
    ThresholdConfig,
    ThresholdVerdict,
    aggregate_metrics,
    evaluate_thresholds,
)
from tests.evaluation.runner import EvaluationReport, EvaluationRunner

__all__ = [
    "EvalDataset",
    "EvalQuery",
    "EvaluationMetrics",
    "EvaluationReport",
    "EvaluationRunner",
    "QueryResult",
    "ThresholdConfig",
    "ThresholdVerdict",
    "aggregate_metrics",
    "evaluate_thresholds",
    "load_dataset",
    "save_dataset",
]
