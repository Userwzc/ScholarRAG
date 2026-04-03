#!/usr/bin/env python3
"""
Offline evaluation runner for ScholarRAG.

This module provides a deterministic evaluation pipeline that:
- Loads evaluation datasets from JSON fixtures
- Runs retrieval queries against the vector store
- Calculates version-aware and provenance-aware metrics
- Generates machine-readable JSON reports
- Exits non-zero when thresholds are missed
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tests.evaluation.dataset import EvalDataset, EvalQuery, load_dataset
from tests.evaluation.metrics import (
    EvaluationMetrics,
    QueryResult,
    ThresholdConfig,
    ThresholdVerdict,
    aggregate_metrics,
    check_citation_coverage,
    check_version_leak,
    evaluate_thresholds,
)


@dataclass
class EvaluationReport:
    """
    Complete evaluation report with metadata.

    Attributes:
        timestamp: ISO 8601 timestamp of evaluation
        dataset_name: Name of the evaluation dataset
        dataset_version: Version of the evaluation dataset
        mode: Retrieval mode used (e.g., "hybrid-only")
        top_k: Number of results retrieved per query
        metrics: Aggregated evaluation metrics
        thresholds: Threshold configuration used
        verdict: Pass/fail verdict
    """

    timestamp: str
    dataset_name: str
    dataset_version: str
    mode: str = "hybrid-only"
    top_k: int = 5
    metrics: EvaluationMetrics = field(default_factory=EvaluationMetrics)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    verdict: ThresholdVerdict = field(
        default_factory=lambda: ThresholdVerdict(passed=True)
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "dataset_name": self.dataset_name,
            "dataset_version": self.dataset_version,
            "mode": self.mode,
            "top_k": self.top_k,
            "metrics": self.metrics.to_dict(),
            "thresholds": self.thresholds.to_dict(),
            "verdict": self.verdict.to_dict(),
        }


class EvaluationRunner:
    """
    Offline evaluation runner for ScholarRAG.

    This class orchestrates the evaluation pipeline:
    1. Load dataset from JSON fixture
    2. Run retrieval queries
    3. Calculate metrics
    4. Evaluate thresholds
    5. Generate report

    Example:
        runner = EvaluationRunner()
        report = runner.run()
        if not report.verdict.passed:
            sys.exit(1)
    """

    def __init__(
        self,
        dataset_path: str | Path | None = None,
        output_path: str | Path | None = None,
        thresholds: ThresholdConfig | None = None,
        top_k: int = 5,
        mode: str = "hybrid-only",
    ) -> None:
        """
        Initialize the evaluation runner.

        Args:
            dataset_path: Path to evaluation dataset JSON (None for default)
            output_path: Path to write report JSON (None for default)
            thresholds: Threshold configuration (None for defaults)
            top_k: Number of results to retrieve per query
            mode: Retrieval mode label
        """
        self.dataset_path = Path(dataset_path) if dataset_path else None
        self.output_path = Path(output_path) if output_path else None
        self.thresholds = thresholds or ThresholdConfig()
        self.top_k = top_k
        self.mode = mode
        self._vector_store: Any = None

    def _get_vector_store(self) -> Any:
        """Get vector store instance (lazy initialization)."""
        if self._vector_store is None:
            from src.rag.vector_store import get_vector_store

            self._vector_store = get_vector_store()
        return self._vector_store

    def _check_vector_store_available(self) -> bool:
        """Check if vector store has data available."""
        try:
            store = self._get_vector_store()
            papers = store.get_all_papers()
            return len(papers) > 0
        except Exception:
            return False

    def _evaluate_query(self, query: EvalQuery) -> QueryResult:
        """
        Evaluate a single query.

        Args:
            query: The evaluation query

        Returns:
            QueryResult with evaluation outcomes
        """
        try:
            store = self._get_vector_store()
            search_results = store.similarity_search(
                query.question,
                k=self.top_k,
            )
        except Exception as e:
            return QueryResult(
                question=query.question,
                failed=True,
                error_message=str(e),
            )

        pdf_hit = False
        page_hit = False
        keyword_hits = 0
        citation_coverage = False
        version_leak = False
        retrieved_chunks: list[dict[str, Any]] = []

        for result in search_results:
            payload = result.get("payload", {})
            metadata = payload.get("metadata", {})

            # Extract chunk info for provenance checks
            chunk_info = {
                "pdf_name": metadata.get("pdf_name", ""),
                "page": metadata.get("page_idx"),
                "type": metadata.get("chunk_type", "text"),
                "chunk_id": metadata.get("chunk_id") or payload.get("id"),
                "paper_version": metadata.get("paper_version"),
                "heading": metadata.get("heading"),
                "is_current": metadata.get("is_current"),
            }
            retrieved_chunks.append(chunk_info)

            # Check PDF hit
            if query.expected_pdf:
                pdf_name = metadata.get("pdf_name", "")
                if query.expected_pdf.lower() in pdf_name.lower():
                    pdf_hit = True

            # Check page hit
            if query.expected_pages:
                page_idx = metadata.get("page_idx")
                if page_idx in query.expected_pages:
                    page_hit = True

            # Check keywords
            content = payload.get("page_content", "")
            for keyword in query.keywords:
                if keyword.lower() in content.lower():
                    keyword_hits += 1

            # Check citation coverage
            if check_citation_coverage({"metadata": metadata}):
                citation_coverage = True

        # Check version leak across all results
        version_leak = check_version_leak(
            [
                {"metadata": r.get("payload", {}).get("metadata", {})}
                for r in search_results
            ]
        )

        return QueryResult(
            question=query.question,
            pdf_hit=pdf_hit,
            page_hit=page_hit,
            keyword_hits=keyword_hits,
            keyword_total=len(query.keywords),
            citation_coverage=citation_coverage,
            version_leak=version_leak,
            result_count=len(search_results),
            retrieved_chunks=retrieved_chunks,
        )

    def run(self, dataset: EvalDataset | None = None) -> EvaluationReport:
        """
        Run the evaluation pipeline.

        Args:
            dataset: Evaluation dataset (None to load from path or default)

        Returns:
            EvaluationReport with metrics and verdict

        Raises:
            RuntimeError: If vector store is unavailable
        """
        # Load dataset
        if dataset is None:
            if self.dataset_path:
                dataset = load_dataset(self.dataset_path)
            else:
                dataset = load_dataset()

        # Check vector store availability
        if not self._check_vector_store_available():
            raise RuntimeError(
                "Vector store is empty or unavailable. "
                "Please add papers before running evaluation."
            )

        # Evaluate queries
        results: list[QueryResult] = []
        for query in dataset.queries:
            result = self._evaluate_query(query)
            results.append(result)

        # Aggregate metrics
        metrics = aggregate_metrics(results)

        # Evaluate thresholds
        verdict = evaluate_thresholds(metrics, self.thresholds)

        # Build report
        report = EvaluationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            dataset_name=dataset.name,
            dataset_version=dataset.version,
            mode=self.mode,
            top_k=self.top_k,
            metrics=metrics,
            thresholds=self.thresholds,
            verdict=verdict,
        )

        return report

    def save_report(self, report: EvaluationReport, path: Path | None = None) -> Path:
        """
        Save evaluation report to JSON file.

        Args:
            report: The evaluation report
            path: Output path (None for default)

        Returns:
            Path to the saved report
        """
        output_path = path or self.output_path or self._get_default_output_path()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

        return output_path

    def _get_default_output_path(self) -> Path:
        """Get default output path for evaluation report."""
        return Path(__file__).parent / "evaluation_report.json"


def parse_threshold_arg(arg: str) -> tuple[str, float]:
    """Parse a threshold argument like 'retrieval_hit_rate=0.6'."""
    if "=" not in arg:
        raise ValueError(f"Invalid threshold format: {arg}. Expected 'name=value'.")

    name, value_str = arg.split("=", 1)
    try:
        value = float(value_str)
    except ValueError:
        raise ValueError(f"Invalid threshold value: {value_str}") from None

    return name.strip(), value


def create_threshold_config_from_args(args: list[str]) -> ThresholdConfig:
    """Create ThresholdConfig from command-line arguments."""
    config = ThresholdConfig()

    for arg in args:
        name, value = parse_threshold_arg(arg)
        if hasattr(config, name):
            setattr(config, name, value)
        else:
            raise ValueError(f"Unknown threshold: {name}")

    return config


def print_report_summary(report: EvaluationReport) -> None:
    """Print a human-readable summary of the evaluation report."""
    print(f"\n{'=' * 60}")
    print("ScholarRAG Offline Evaluation Report")
    print(f"{'=' * 60}")
    print(f"Timestamp: {report.timestamp}")
    print(f"Dataset: {report.dataset_name} v{report.dataset_version}")
    print(f"Mode: {report.mode}")
    print(f"Top-K: {report.top_k}")
    print(f"\n{'─' * 40}")
    print("Metrics:")
    print(f"  Total Queries: {report.metrics.total_queries}")
    print(f"  Retrieval Hit Rate: {report.metrics.retrieval_hit_rate:.2%}")
    print(f"  Page Hit Rate: {report.metrics.page_hit_rate:.2%}")
    print(f"  Keyword Match Rate: {report.metrics.keyword_match_rate:.2%}")
    print(f"  Citation Coverage Rate: {report.metrics.citation_coverage_rate:.2%}")
    print(
        f"  Current Version Leak Rate: {report.metrics.current_version_leak_rate:.2%}"
    )
    print(f"  Failed Query Rate: {report.metrics.failed_query_rate:.2%}")
    print(f"\n{'─' * 40}")
    print("Thresholds:")
    print(f"  Retrieval Hit Rate >= {report.thresholds.retrieval_hit_rate:.2%}")
    print(f"  Page Hit Rate >= {report.thresholds.page_hit_rate:.2%}")
    print(f"  Keyword Match Rate >= {report.thresholds.keyword_match_rate:.2%}")
    print(f"  Citation Coverage Rate >= {report.thresholds.citation_coverage_rate:.2%}")
    print(
        f"  Current Version Leak Rate <= {report.thresholds.current_version_leak_rate:.2%}"
    )
    print(f"  Failed Query Rate <= {report.thresholds.failed_query_rate:.2%}")
    print(f"\n{'─' * 40}")

    if report.verdict.passed:
        print("Verdict: PASSED ✓")
    else:
        print("Verdict: FAILED ✗")
        print("\nFailures:")
        for failure in report.verdict.failures:
            print(f"  - {failure}")

    print(f"{'=' * 60}\n")


def main() -> int:
    """
    Main entry point for the evaluation runner.

    Returns:
        Exit code (0 for success, 1 for threshold failure, 2 for error)
    """
    parser = argparse.ArgumentParser(
        description="Run offline evaluation for ScholarRAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tests.evaluation.runner
  python -m tests.evaluation.runner --dataset my_dataset.json
  python -m tests.evaluation.runner --output report.json
  python -m tests.evaluation.runner --thresholds retrieval_hit_rate=0.6 page_hit_rate=0.4
        """,
    )

    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="Path to evaluation dataset JSON (default: built-in dataset)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to output report JSON (default: tests/evaluation/evaluation_report.json)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of results to retrieve per query (default: 5)",
    )
    parser.add_argument(
        "--thresholds",
        nargs="*",
        default=[],
        help="Threshold overrides in format 'name=value' (e.g., retrieval_hit_rate=0.6)",
    )
    parser.add_argument(
        "--thresholds-file",
        type=str,
        default=None,
        help="Path to JSON file containing threshold configuration",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress summary output",
    )

    args = parser.parse_args()

    try:
        if args.thresholds_file:
            with open(args.thresholds_file, "r", encoding="utf-8") as f:
                threshold_data = json.load(f)
            thresholds = ThresholdConfig.from_dict(threshold_data)
        else:
            thresholds = create_threshold_config_from_args(args.thresholds)
    except FileNotFoundError as e:
        print(f"Error: Thresholds file not found: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in thresholds file: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # Create runner
    runner = EvaluationRunner(
        dataset_path=args.dataset,
        output_path=args.output,
        thresholds=thresholds,
        top_k=args.top_k,
    )

    # Run evaluation
    try:
        report = runner.run()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 2

    # Save report
    output_path = runner.save_report(report)

    # Print summary
    if not args.quiet:
        print_report_summary(report)
        print(f"Report saved to: {output_path}")

    # Return exit code based on verdict
    return 0 if report.verdict.passed else 1


if __name__ == "__main__":
    sys.exit(main())
