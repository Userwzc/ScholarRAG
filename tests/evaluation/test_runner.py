"""
Tests for the offline evaluation runner and metrics.

These tests verify:
- Dataset loading and serialization
- Metric calculations
- Threshold evaluation
- Runner execution with mock vector store
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.evaluation.dataset import (
    DEFAULT_DATASET,
    EvalDataset,
    EvalQuery,
    load_dataset,
    save_dataset,
)
from tests.evaluation.metrics import (
    EvaluationMetrics,
    QueryResult,
    ThresholdConfig,
    ThresholdVerdict,
    aggregate_metrics,
    calculate_citation_coverage_rate,
    calculate_current_version_leak_rate,
    calculate_failed_query_rate,
    calculate_keyword_match_rate,
    calculate_page_hit_rate,
    calculate_retrieval_hit_rate,
    check_citation_coverage,
    check_version_leak,
    evaluate_thresholds,
)
from tests.evaluation.runner import (
    EvaluationReport,
    EvaluationRunner,
    create_threshold_config_from_args,
    parse_threshold_arg,
)


# ============================================================================
# Dataset Tests
# ============================================================================


class TestEvalQuery:
    """Tests for EvalQuery dataclass."""

    def test_to_dict_and_from_dict(self) -> None:
        """Test serialization round-trip."""
        query = EvalQuery(
            question="What is the methodology?",
            expected_pdf="dream",
            expected_pages=[2, 3],
            keywords=["methodology", "approach"],
            expected_chunk_ids=["chunk-1", "chunk-2"],
            expected_version=1,
        )

        data = query.to_dict()
        restored = EvalQuery.from_dict(data)

        assert restored.question == query.question
        assert restored.expected_pdf == query.expected_pdf
        assert restored.expected_pages == query.expected_pages
        assert restored.keywords == query.keywords
        assert restored.expected_chunk_ids == query.expected_chunk_ids
        assert restored.expected_version == query.expected_version

    def test_defaults(self) -> None:
        """Test default values."""
        query = EvalQuery(question="Test question")

        assert query.expected_pdf == ""
        assert query.expected_pages == []
        assert query.keywords == []
        assert query.expected_chunk_ids == []
        assert query.expected_version is None


class TestEvalDataset:
    """Tests for EvalDataset dataclass."""

    def test_to_dict_and_from_dict(self) -> None:
        """Test serialization round-trip."""
        dataset = EvalDataset(
            name="test_dataset",
            version="2.0",
            description="Test description",
            queries=[
                EvalQuery(question="Q1", expected_pdf="paper1"),
                EvalQuery(question="Q2", expected_pdf="paper2"),
            ],
        )

        data = dataset.to_dict()
        restored = EvalDataset.from_dict(data)

        assert restored.name == dataset.name
        assert restored.version == dataset.version
        assert restored.description == dataset.description
        assert len(restored.queries) == 2

    def test_default_dataset(self) -> None:
        """Test default dataset has expected structure."""
        assert DEFAULT_DATASET.name == "scholarrag_regression"
        assert len(DEFAULT_DATASET.queries) >= 1

    def test_load_and_save_dataset(self) -> None:
        """Test loading and saving dataset to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_dataset.json"

            # Save
            save_dataset(DEFAULT_DATASET, path)
            assert path.exists()

            # Load
            loaded = load_dataset(path)
            assert loaded.name == DEFAULT_DATASET.name
            assert len(loaded.queries) == len(DEFAULT_DATASET.queries)


# ============================================================================
# Metrics Tests
# ============================================================================


class TestQueryResult:
    """Tests for QueryResult dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization."""
        result = QueryResult(
            question="Test question",
            pdf_hit=True,
            page_hit=False,
            keyword_hits=2,
            keyword_total=3,
            citation_coverage=True,
            version_leak=False,
            failed=False,
            result_count=5,
        )

        data = result.to_dict()

        assert data["question"] == "Test question"
        assert data["pdf_hit"] is True
        assert data["page_hit"] is False
        assert data["keyword_hits"] == 2
        assert data["keyword_total"] == 3
        assert data["citation_coverage"] is True
        assert data["version_leak"] is False
        assert data["failed"] is False
        assert data["result_count"] == 5


class TestMetricCalculations:
    """Tests for metric calculation functions."""

    def test_calculate_retrieval_hit_rate(self) -> None:
        """Test retrieval hit rate calculation."""
        results = [
            QueryResult(question="Q1", pdf_hit=True),
            QueryResult(question="Q2", pdf_hit=False),
            QueryResult(question="Q3", pdf_hit=True),
        ]

        rate = calculate_retrieval_hit_rate(results)
        assert rate == 2 / 3

    def test_calculate_retrieval_hit_rate_empty(self) -> None:
        """Test retrieval hit rate with empty results."""
        rate = calculate_retrieval_hit_rate([])
        assert rate == 0.0

    def test_calculate_retrieval_hit_rate_with_failures(self) -> None:
        """Test retrieval hit rate excludes failed queries."""
        results = [
            QueryResult(question="Q1", pdf_hit=True),
            QueryResult(question="Q2", pdf_hit=False, failed=True),
            QueryResult(question="Q3", pdf_hit=True),
        ]

        rate = calculate_retrieval_hit_rate(results)
        # Only Q1 and Q3 are non-failed, both hit
        assert rate == 2 / 2

    def test_calculate_page_hit_rate(self) -> None:
        """Test page hit rate calculation."""
        results = [
            QueryResult(question="Q1", page_hit=True),
            QueryResult(question="Q2", page_hit=False),
            QueryResult(question="Q3", page_hit=True),
        ]

        rate = calculate_page_hit_rate(results)
        assert rate == 2 / 3

    def test_calculate_keyword_match_rate(self) -> None:
        """Test keyword match rate calculation."""
        results = [
            QueryResult(question="Q1", keyword_hits=2, keyword_total=3),
            QueryResult(question="Q2", keyword_hits=1, keyword_total=2),
        ]

        rate = calculate_keyword_match_rate(results)
        # (2/3 + 1/2) / 2 = (0.667 + 0.5) / 2 = 0.583
        assert abs(rate - (2 / 3 + 1 / 2) / 2) < 0.01

    def test_calculate_keyword_match_rate_zero_keywords(self) -> None:
        """Test keyword match rate with zero keywords."""
        results = [
            QueryResult(question="Q1", keyword_hits=0, keyword_total=0),
        ]

        rate = calculate_keyword_match_rate(results)
        assert rate == 0.0

    def test_calculate_citation_coverage_rate(self) -> None:
        """Test citation coverage rate calculation."""
        results = [
            QueryResult(question="Q1", citation_coverage=True, result_count=5),
            QueryResult(question="Q2", citation_coverage=False, result_count=3),
            QueryResult(question="Q3", citation_coverage=True, result_count=2),
        ]

        rate = calculate_citation_coverage_rate(results)
        assert rate == 2 / 3

    def test_calculate_citation_coverage_rate_no_results(self) -> None:
        """Test citation coverage rate with no results."""
        results = [
            QueryResult(question="Q1", citation_coverage=False, result_count=0),
        ]

        rate = calculate_citation_coverage_rate(results)
        assert rate == 0.0

    def test_calculate_current_version_leak_rate(self) -> None:
        """Test version leak rate calculation."""
        results = [
            QueryResult(question="Q1", version_leak=False, result_count=5),
            QueryResult(question="Q2", version_leak=True, result_count=3),
            QueryResult(question="Q3", version_leak=False, result_count=2),
        ]

        rate = calculate_current_version_leak_rate(results)
        assert rate == 1 / 3

    def test_calculate_failed_query_rate(self) -> None:
        """Test failed query rate calculation."""
        results = [
            QueryResult(question="Q1", failed=False),
            QueryResult(question="Q2", failed=True),
            QueryResult(question="Q3", failed=False),
        ]

        rate = calculate_failed_query_rate(results)
        assert rate == 1 / 3

    def test_aggregate_metrics(self) -> None:
        """Test metrics aggregation."""
        results = [
            QueryResult(question="Q1", pdf_hit=True, page_hit=True, keyword_hits=2, keyword_total=3),
            QueryResult(question="Q2", pdf_hit=False, page_hit=False, keyword_hits=1, keyword_total=2),
        ]

        metrics = aggregate_metrics(results)

        assert metrics.total_queries == 2
        assert metrics.retrieval_hit_rate == 0.5
        assert metrics.page_hit_rate == 0.5
        assert metrics.failed_query_rate == 0.0


class TestCitationCoverage:
    """Tests for citation coverage checking."""

    def test_check_citation_coverage_valid(self) -> None:
        """Test valid citation coverage."""
        chunk = {
            "metadata": {
                "pdf_name": "test_paper",
                "page": 1,
                "type": "text",
            }
        }

        assert check_citation_coverage(chunk) is True

    def test_check_citation_coverage_missing_pdf_name(self) -> None:
        """Test missing pdf_name."""
        chunk = {
            "metadata": {
                "page": 1,
                "type": "text",
            }
        }

        assert check_citation_coverage(chunk) is False

    def test_check_citation_coverage_empty_pdf_name(self) -> None:
        """Test empty pdf_name."""
        chunk = {
            "metadata": {
                "pdf_name": "",
                "page": 1,
                "type": "text",
            }
        }

        assert check_citation_coverage(chunk) is False

    def test_check_citation_coverage_missing_page(self) -> None:
        """Test missing page."""
        chunk = {
            "metadata": {
                "pdf_name": "test_paper",
                "type": "text",
            }
        }

        assert check_citation_coverage(chunk) is False


class TestVersionLeak:
    """Tests for version leak detection."""

    def test_check_version_leak_no_leak(self) -> None:
        """Test no version leak."""
        chunks = [
            {"metadata": {"is_current": True}},
            {"metadata": {"is_current": None}},  # Not set is OK
            {"metadata": {}},  # Missing is OK
        ]

        assert check_version_leak(chunks) is False

    def test_check_version_leak_detected(self) -> None:
        """Test version leak detected."""
        chunks = [
            {"metadata": {"is_current": True}},
            {"metadata": {"is_current": False}},  # Leak!
        ]

        assert check_version_leak(chunks) is True


class TestThresholdEvaluation:
    """Tests for threshold evaluation."""

    def test_evaluate_thresholds_pass(self) -> None:
        """Test passing all thresholds."""
        metrics = EvaluationMetrics(
            total_queries=10,
            retrieval_hit_rate=0.8,
            page_hit_rate=0.6,
            keyword_match_rate=0.5,
            citation_coverage_rate=0.9,
            current_version_leak_rate=0.0,
            failed_query_rate=0.0,
        )

        thresholds = ThresholdConfig(
            retrieval_hit_rate=0.5,
            page_hit_rate=0.3,
            keyword_match_rate=0.3,
            citation_coverage_rate=0.8,
            current_version_leak_rate=0.0,
            failed_query_rate=0.1,
        )

        verdict = evaluate_thresholds(metrics, thresholds)

        assert verdict.passed is True
        assert len(verdict.failures) == 0

    def test_evaluate_thresholds_fail(self) -> None:
        """Test failing thresholds."""
        metrics = EvaluationMetrics(
            total_queries=10,
            retrieval_hit_rate=0.3,  # Below threshold
            page_hit_rate=0.6,
            keyword_match_rate=0.5,
            citation_coverage_rate=0.9,
            current_version_leak_rate=0.1,  # Above threshold
            failed_query_rate=0.0,
        )

        thresholds = ThresholdConfig(
            retrieval_hit_rate=0.5,
            page_hit_rate=0.3,
            keyword_match_rate=0.3,
            citation_coverage_rate=0.8,
            current_version_leak_rate=0.0,
            failed_query_rate=0.1,
        )

        verdict = evaluate_thresholds(metrics, thresholds)

        assert verdict.passed is False
        assert len(verdict.failures) == 2
        assert any("retrieval_hit_rate" in f for f in verdict.failures)
        assert any("current_version_leak_rate" in f for f in verdict.failures)


# ============================================================================
# Runner Tests
# ============================================================================


class TestEvaluationRunner:
    """Tests for EvaluationRunner."""

    def test_parse_threshold_arg(self) -> None:
        """Test threshold argument parsing."""
        name, value = parse_threshold_arg("retrieval_hit_rate=0.6")
        assert name == "retrieval_hit_rate"
        assert value == 0.6

    def test_parse_threshold_arg_invalid(self) -> None:
        """Test invalid threshold argument."""
        with pytest.raises(ValueError):
            parse_threshold_arg("invalid")

        with pytest.raises(ValueError):
            parse_threshold_arg("name=not_a_number")

    def test_create_threshold_config_from_args(self) -> None:
        """Test creating threshold config from args."""
        config = create_threshold_config_from_args([
            "retrieval_hit_rate=0.6",
            "page_hit_rate=0.4",
        ])

        assert config.retrieval_hit_rate == 0.6
        assert config.page_hit_rate == 0.4

    def test_create_threshold_config_unknown_threshold(self) -> None:
        """Test unknown threshold raises error."""
        with pytest.raises(ValueError):
            create_threshold_config_from_args(["unknown_threshold=0.5"])

    def test_runner_with_mock_vector_store(self, mock_vector_store: MagicMock) -> None:
        """Test runner with mock vector store."""
        # Add some test data to mock store
        mock_vector_store.add_multimodal(
            inputs=[{"text": "DREAM methodology approach framework"}],
            metadatas=[{
                "pdf_name": "dream_paper",
                "page_idx": 2,
                "chunk_type": "text",
                "heading": "Methodology",
                "is_current": True,
            }],
        )

        # Create a simple dataset
        dataset = EvalDataset(
            name="test",
            queries=[
                EvalQuery(
                    question="What is the methodology?",
                    expected_pdf="dream",
                    expected_pages=[2],
                    keywords=["methodology"],
                ),
            ],
        )

        # Create runner with mock
        runner = EvaluationRunner()
        runner._vector_store = mock_vector_store

        # Mock _check_vector_store_available
        with patch.object(runner, "_check_vector_store_available", return_value=True):
            report = runner.run(dataset)

        assert report.metrics.total_queries == 1
        assert report.metrics.retrieval_hit_rate >= 0.0
        assert report.verdict is not None

    def test_runner_raises_on_empty_vector_store(self) -> None:
        """Test runner raises error when vector store is empty."""
        runner = EvaluationRunner()

        with patch.object(runner, "_check_vector_store_available", return_value=False):
            with pytest.raises(RuntimeError, match="Vector store is empty"):
                runner.run()

    def test_save_report(self) -> None:
        """Test saving evaluation report."""
        report = EvaluationReport(
            timestamp="2024-01-01T00:00:00Z",
            dataset_name="test",
            dataset_version="1.0",
            metrics=EvaluationMetrics(total_queries=1),
            verdict=ThresholdVerdict(passed=True),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.json"
            runner = EvaluationRunner()
            saved_path = runner.save_report(report, path)

            assert saved_path.exists()

            # Verify JSON is valid
            with open(saved_path) as f:
                data = json.load(f)

            assert data["dataset_name"] == "test"
            assert data["verdict"]["passed"] is True


class TestEvaluationReport:
    """Tests for EvaluationReport."""

    def test_to_dict(self) -> None:
        """Test report serialization."""
        report = EvaluationReport(
            timestamp="2024-01-01T00:00:00Z",
            dataset_name="test_dataset",
            dataset_version="1.0",
            mode="hybrid-only",
            top_k=5,
            metrics=EvaluationMetrics(
                total_queries=10,
                retrieval_hit_rate=0.8,
            ),
            thresholds=ThresholdConfig(retrieval_hit_rate=0.5),
            verdict=ThresholdVerdict(passed=True),
        )

        data = report.to_dict()

        assert data["timestamp"] == "2024-01-01T00:00:00Z"
        assert data["dataset_name"] == "test_dataset"
        assert data["mode"] == "hybrid-only"
        assert data["top_k"] == 5
        assert data["metrics"]["total_queries"] == 10
        assert data["thresholds"]["retrieval_hit_rate"] == 0.5
        assert data["verdict"]["passed"] is True


# ============================================================================
# Integration Tests (marked as integration)
# ============================================================================


@pytest.mark.integration
class TestRunnerIntegration:
    """Integration tests requiring real vector store."""

    def test_runner_with_real_vector_store(self) -> None:
        """Test runner with real vector store (requires Qdrant)."""
        pytest.skip("Integration test - requires Qdrant and papers")

    def test_runner_cli(self) -> None:
        """Test runner CLI execution."""
        pytest.skip("Integration test - requires Qdrant and papers")
