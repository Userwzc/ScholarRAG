"""
Evaluation dataset module for offline regression testing.

This module provides data structures and loading utilities for
deterministic evaluation datasets used in the offline evaluation pipeline.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvalQuery:
    """
    A single evaluation query with expected results.

    Attributes:
        question: The query text to evaluate
        expected_pdf: Expected paper name (partial match allowed)
        expected_pages: List of expected page numbers (0-indexed)
        keywords: Keywords that should appear in retrieved content
        expected_chunk_ids: Optional list of expected chunk IDs
        expected_version: Optional expected paper version
    """

    question: str
    expected_pdf: str = ""
    expected_pages: list[int] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    expected_chunk_ids: list[str] = field(default_factory=list)
    expected_version: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "question": self.question,
            "expected_pdf": self.expected_pdf,
            "expected_pages": self.expected_pages,
            "keywords": self.keywords,
            "expected_chunk_ids": self.expected_chunk_ids,
            "expected_version": self.expected_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalQuery":
        """Create from dictionary."""
        return cls(
            question=data.get("question", ""),
            expected_pdf=data.get("expected_pdf", ""),
            expected_pages=data.get("expected_pages", []),
            keywords=data.get("keywords", []),
            expected_chunk_ids=data.get("expected_chunk_ids", []),
            expected_version=data.get("expected_version"),
        )


@dataclass
class EvalDataset:
    """
    A collection of evaluation queries with metadata.

    Attributes:
        name: Dataset name
        version: Dataset version string
        description: Human-readable description
        queries: List of evaluation queries
    """

    name: str
    version: str = "1.0"
    description: str = ""
    queries: list[EvalQuery] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "queries": [q.to_dict() for q in self.queries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalDataset":
        """Create from dictionary."""
        queries = [EvalQuery.from_dict(q) for q in data.get("queries", [])]
        return cls(
            name=data.get("name", "unnamed"),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
            queries=queries,
        )


# Default evaluation dataset for regression testing
DEFAULT_DATASET = EvalDataset(
    name="scholarrag_regression",
    version="1.0",
    description="Default regression dataset for ScholarRAG offline evaluation",
    queries=[
        EvalQuery(
            question="What is the core methodology of the DREAM paper?",
            expected_pdf="dream",
            expected_pages=[2, 3],
            keywords=["methodology", "approach", "framework"],
        ),
        EvalQuery(
            question="How does the model handle multimodal inputs?",
            expected_pdf="dream",
            expected_pages=[2, 4],
            keywords=["multimodal", "input", "fusion"],
        ),
        EvalQuery(
            question="What are the experimental results?",
            expected_pdf="dream",
            expected_pages=[3, 5],
            keywords=["results", "accuracy", "benchmark"],
        ),
        EvalQuery(
            question="Describe the attention mechanism in transformers.",
            expected_pdf="attention",
            expected_pages=[1, 2],
            keywords=["attention", "transformer", "mechanism"],
        ),
        EvalQuery(
            question="What is BERT's pre-training objective?",
            expected_pdf="bert",
            expected_pages=[2, 3],
            keywords=["bert", "pre-training", "objective"],
        ),
    ],
)


def load_dataset(path: str | Path | None = None) -> EvalDataset:
    """
    Load an evaluation dataset from a JSON file.

    Args:
        path: Path to the dataset JSON file. If None, returns the default dataset.

    Returns:
        EvalDataset instance

    Raises:
        FileNotFoundError: If the specified file does not exist
        json.JSONDecodeError: If the file is not valid JSON
        ValueError: If the dataset structure is invalid
    """
    if path is None:
        return DEFAULT_DATASET

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    return EvalDataset.from_dict(data)


def save_dataset(dataset: EvalDataset, path: str | Path) -> None:
    """
    Save an evaluation dataset to a JSON file.

    Args:
        dataset: The dataset to save
        path: Output file path
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(dataset.to_dict(), f, ensure_ascii=False, indent=2)


def get_default_dataset_path() -> Path:
    """Get the default path for the evaluation dataset fixture."""
    return Path(__file__).parent / "fixtures" / "eval_dataset.json"


def ensure_default_dataset_fixture() -> Path:
    """
    Ensure the default dataset fixture file exists.

    Creates the fixture file if it doesn't exist.

    Returns:
        Path to the fixture file
    """
    path = get_default_dataset_path()
    if not path.exists():
        save_dataset(DEFAULT_DATASET, path)
    return path
