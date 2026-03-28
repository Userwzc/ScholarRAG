"""
Evaluation metrics for offline regression testing.

This module provides deterministic metric calculations for evaluating
retrieval quality, citation coverage, and version-awareness.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryResult:
    """
    Result of evaluating a single query.

    Attributes:
        question: The query text
        pdf_hit: Whether the expected PDF was found in results
        page_hit: Whether an expected page was found in results
        keyword_hits: Number of keywords found in retrieved content
        keyword_total: Total keywords expected
        citation_coverage: Whether citations have required fields
        version_leak: Whether non-current versions leaked into results
        failed: Whether the query failed to execute
        error_message: Error message if failed
        result_count: Number of results returned
        retrieved_chunks: List of retrieved chunk metadata
    """

    question: str
    pdf_hit: bool = False
    page_hit: bool = False
    keyword_hits: int = 0
    keyword_total: int = 0
    citation_coverage: bool = False
    version_leak: bool = False
    failed: bool = False
    error_message: str | None = None
    result_count: int = 0
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "question": self.question,
            "pdf_hit": self.pdf_hit,
            "page_hit": self.page_hit,
            "keyword_hits": self.keyword_hits,
            "keyword_total": self.keyword_total,
            "citation_coverage": self.citation_coverage,
            "version_leak": self.version_leak,
            "failed": self.failed,
            "error_message": self.error_message,
            "result_count": self.result_count,
        }


@dataclass
class EvaluationMetrics:
    """
    Aggregated evaluation metrics.

    Attributes:
        total_queries: Total number of queries evaluated
        retrieval_hit_rate: Fraction of queries with PDF hit
        page_hit_rate: Fraction of queries with page hit
        keyword_match_rate: Average keyword match ratio
        citation_coverage_rate: Fraction of queries with proper citations
        current_version_leak_rate: Fraction of queries with version leaks
        failed_query_rate: Fraction of queries that failed
        query_results: Individual query results
    """

    total_queries: int = 0
    retrieval_hit_rate: float = 0.0
    page_hit_rate: float = 0.0
    keyword_match_rate: float = 0.0
    citation_coverage_rate: float = 0.0
    current_version_leak_rate: float = 0.0
    failed_query_rate: float = 0.0
    query_results: list[QueryResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_queries": self.total_queries,
            "retrieval_hit_rate": self.retrieval_hit_rate,
            "page_hit_rate": self.page_hit_rate,
            "keyword_match_rate": self.keyword_match_rate,
            "citation_coverage_rate": self.citation_coverage_rate,
            "current_version_leak_rate": self.current_version_leak_rate,
            "failed_query_rate": self.failed_query_rate,
            "query_results": [r.to_dict() for r in self.query_results],
        }


def calculate_retrieval_hit_rate(results: list[QueryResult]) -> float:
    """
    Calculate the fraction of queries where the expected PDF was found.

    Args:
        results: List of query results

    Returns:
        Hit rate as a fraction (0.0 to 1.0)
    """
    if not results:
        return 0.0

    hits = sum(1 for r in results if r.pdf_hit and not r.failed)
    total = sum(1 for r in results if not r.failed)

    return hits / total if total > 0 else 0.0


def calculate_page_hit_rate(results: list[QueryResult]) -> float:
    """
    Calculate the fraction of queries where an expected page was found.

    Args:
        results: List of query results

    Returns:
        Hit rate as a fraction (0.0 to 1.0)
    """
    if not results:
        return 0.0

    hits = sum(1 for r in results if r.page_hit and not r.failed)
    total = sum(1 for r in results if not r.failed)

    return hits / total if total > 0 else 0.0


def calculate_keyword_match_rate(results: list[QueryResult]) -> float:
    """
    Calculate the average keyword match ratio across queries.

    Args:
        results: List of query results

    Returns:
        Average match ratio (0.0 to 1.0)
    """
    if not results:
        return 0.0

    ratios = []
    for r in results:
        if r.failed or r.keyword_total == 0:
            continue
        ratios.append(r.keyword_hits / r.keyword_total)

    return sum(ratios) / len(ratios) if ratios else 0.0


def calculate_citation_coverage_rate(results: list[QueryResult]) -> float:
    """
    Calculate the fraction of queries with proper citation fields.

    A query has proper citation coverage if:
    - It returned results
    - At least one result has required provenance fields (pdf_name, page, type)

    Args:
        results: List of query results

    Returns:
        Coverage rate as a fraction (0.0 to 1.0)
    """
    if not results:
        return 0.0

    covered = sum(1 for r in results if r.citation_coverage and not r.failed)
    total = sum(1 for r in results if not r.failed and r.result_count > 0)

    return covered / total if total > 0 else 0.0


def calculate_current_version_leak_rate(results: list[QueryResult]) -> float:
    """
    Calculate the fraction of queries where non-current versions leaked.

    A version leak occurs when:
    - Results contain chunks with is_current=False
    - This should not happen in default retrieval mode

    Args:
        results: List of query results

    Returns:
        Leak rate as a fraction (0.0 to 1.0), lower is better
    """
    if not results:
        return 0.0

    leaks = sum(1 for r in results if r.version_leak and not r.failed)
    total = sum(1 for r in results if not r.failed and r.result_count > 0)

    return leaks / total if total > 0 else 0.0


def calculate_failed_query_rate(results: list[QueryResult]) -> float:
    """
    Calculate the fraction of queries that failed to execute.

    Args:
        results: List of query results

    Returns:
        Failure rate as a fraction (0.0 to 1.0)
    """
    if not results:
        return 0.0

    failed = sum(1 for r in results if r.failed)
    return failed / len(results)


def aggregate_metrics(results: list[QueryResult]) -> EvaluationMetrics:
    """
    Aggregate individual query results into overall metrics.

    Args:
        results: List of query results

    Returns:
        Aggregated metrics
    """
    return EvaluationMetrics(
        total_queries=len(results),
        retrieval_hit_rate=calculate_retrieval_hit_rate(results),
        page_hit_rate=calculate_page_hit_rate(results),
        keyword_match_rate=calculate_keyword_match_rate(results),
        citation_coverage_rate=calculate_citation_coverage_rate(results),
        current_version_leak_rate=calculate_current_version_leak_rate(results),
        failed_query_rate=calculate_failed_query_rate(results),
        query_results=results,
    )


def check_citation_coverage(chunk: dict[str, Any]) -> bool:
    """
    Check if a chunk has the required fields for citation coverage.

    Required fields:
    - pdf_name: Name of the PDF file
    - page_idx: Page index (0-indexed)
    - chunk_type: Chunk type (text/image/table)

    Optional but recommended:
    - chunk_id: Unique identifier
    - paper_version: Version number
    - heading: Section heading

    Args:
        chunk: Chunk metadata dictionary

    Returns:
        True if required fields are present
    """
    metadata = chunk.get("metadata", chunk)

    # Check required fields - handle both stored field names and legacy names
    # Stored metadata uses page_idx and chunk_type, but also accept page and type
    page = (
        metadata.get("page_idx")
        or metadata.get("page")
        or chunk.get("page_idx")
        or chunk.get("page")
    )
    chunk_type = (
        metadata.get("chunk_type")
        or metadata.get("type")
        or chunk.get("chunk_type")
        or chunk.get("type")
    )
    pdf_name = metadata.get("pdf_name") or chunk.get("pdf_name", "")

    if page is None or chunk_type is None or not pdf_name:
        return False

    return True


def check_version_leak(chunks: list[dict[str, Any]]) -> bool:
    """
    Check if any chunks have is_current=False (version leak).

    Args:
        chunks: List of chunk metadata dictionaries

    Returns:
        True if version leak detected
    """
    for chunk in chunks:
        metadata = chunk.get("metadata", chunk)
        is_current = metadata.get("is_current")
        # If is_current is explicitly False, it's a leak
        if is_current is False:
            return True
    return False


@dataclass
class ThresholdConfig:
    """
    Configuration for evaluation thresholds.

    Attributes:
        retrieval_hit_rate: Minimum acceptable retrieval hit rate
        page_hit_rate: Minimum acceptable page hit rate
        keyword_match_rate: Minimum acceptable keyword match rate
        citation_coverage_rate: Minimum acceptable citation coverage rate
        current_version_leak_rate: Maximum acceptable version leak rate
        failed_query_rate: Maximum acceptable failed query rate
    """

    retrieval_hit_rate: float = 0.5
    page_hit_rate: float = 0.3
    keyword_match_rate: float = 0.3
    citation_coverage_rate: float = 0.8
    current_version_leak_rate: float = 0.0  # Zero tolerance for leaks
    failed_query_rate: float = 0.1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "retrieval_hit_rate": self.retrieval_hit_rate,
            "page_hit_rate": self.page_hit_rate,
            "keyword_match_rate": self.keyword_match_rate,
            "citation_coverage_rate": self.citation_coverage_rate,
            "current_version_leak_rate": self.current_version_leak_rate,
            "failed_query_rate": self.failed_query_rate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThresholdConfig":
        """Create from dictionary."""
        return cls(
            retrieval_hit_rate=data.get("retrieval_hit_rate", 0.5),
            page_hit_rate=data.get("page_hit_rate", 0.3),
            keyword_match_rate=data.get("keyword_match_rate", 0.3),
            citation_coverage_rate=data.get("citation_coverage_rate", 0.8),
            current_version_leak_rate=data.get("current_version_leak_rate", 0.0),
            failed_query_rate=data.get("failed_query_rate", 0.1),
        )


@dataclass
class ThresholdVerdict:
    """
    Result of threshold evaluation.

    Attributes:
        passed: Whether all thresholds passed
        failures: List of threshold failures
    """

    passed: bool
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "passed": self.passed,
            "failures": self.failures,
        }


def evaluate_thresholds(
    metrics: EvaluationMetrics,
    thresholds: ThresholdConfig,
) -> ThresholdVerdict:
    """
    Evaluate metrics against thresholds.

    Args:
        metrics: Aggregated evaluation metrics
        thresholds: Threshold configuration

    Returns:
        Threshold verdict with pass/fail status
    """
    failures = []

    # Check retrieval hit rate (must be >= threshold)
    if metrics.retrieval_hit_rate < thresholds.retrieval_hit_rate:
        failures.append(
            f"retrieval_hit_rate {metrics.retrieval_hit_rate:.2%} "
            f"< {thresholds.retrieval_hit_rate:.2%}"
        )

    # Check page hit rate (must be >= threshold)
    if metrics.page_hit_rate < thresholds.page_hit_rate:
        failures.append(
            f"page_hit_rate {metrics.page_hit_rate:.2%} "
            f"< {thresholds.page_hit_rate:.2%}"
        )

    # Check keyword match rate (must be >= threshold)
    if metrics.keyword_match_rate < thresholds.keyword_match_rate:
        failures.append(
            f"keyword_match_rate {metrics.keyword_match_rate:.2%} "
            f"< {thresholds.keyword_match_rate:.2%}"
        )

    # Check citation coverage rate (must be >= threshold)
    if metrics.citation_coverage_rate < thresholds.citation_coverage_rate:
        failures.append(
            f"citation_coverage_rate {metrics.citation_coverage_rate:.2%} "
            f"< {thresholds.citation_coverage_rate:.2%}"
        )

    # Check version leak rate (must be <= threshold)
    if metrics.current_version_leak_rate > thresholds.current_version_leak_rate:
        failures.append(
            f"current_version_leak_rate {metrics.current_version_leak_rate:.2%} "
            f"> {thresholds.current_version_leak_rate:.2%}"
        )

    # Check failed query rate (must be <= threshold)
    if metrics.failed_query_rate > thresholds.failed_query_rate:
        failures.append(
            f"failed_query_rate {metrics.failed_query_rate:.2%} "
            f"> {thresholds.failed_query_rate:.2%}"
        )

    return ThresholdVerdict(
        passed=len(failures) == 0,
        failures=failures,
    )
