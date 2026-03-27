"""Tests for structured provenance emission from the backend query flow."""

from api.schemas import SourceSchema
from src.agent.evidence_builder import build_structured_provenance


class TestBuildStructuredProvenance:
    """Tests for build_structured_provenance function."""

    def test_empty_evidence_returns_empty_list(self) -> None:
        """Empty evidence should return empty provenance list."""
        result = build_structured_provenance([])
        assert result == []

    def test_single_text_evidence(self) -> None:
        """Single text evidence should produce valid provenance."""
        evidence = [
            {
                "evidence_id": "abc123def456",
                "pdf_name": "test_paper",
                "page_idx": 5,
                "chunk_type": "text",
                "heading": "Introduction",
                "text": "This is the introduction section of the paper.",
                "score": 0.85,
            }
        ]

        result = build_structured_provenance(evidence)

        assert len(result) == 1
        source = result[0]
        assert source["pdf_name"] == "test_paper"
        assert source["page"] == 5
        assert source["type"] == "text"
        assert source["chunk_id"] == "abc123def456"
        assert source["heading"] == "Introduction"
        assert source["supporting_text"] == "This is the introduction section of the paper."
        assert source["paper_version"] is None

    def test_multiple_evidence_deduplication(self) -> None:
        """Duplicate (pdf_name, page, type) tuples should be deduplicated."""
        evidence = [
            {
                "evidence_id": "id1",
                "pdf_name": "paper1",
                "page_idx": 1,
                "chunk_type": "text",
                "heading": "Section A",
                "text": "Content A",
                "score": 0.9,
            },
            {
                "evidence_id": "id2",
                "pdf_name": "paper1",
                "page_idx": 1,
                "chunk_type": "text",
                "heading": "Section B",
                "text": "Content B",
                "score": 0.8,
            },
            {
                "evidence_id": "id3",
                "pdf_name": "paper1",
                "page_idx": 2,
                "chunk_type": "text",
                "heading": "Section C",
                "text": "Content C",
                "score": 0.7,
            },
        ]

        result = build_structured_provenance(evidence)

        assert len(result) == 2
        pdf_pages = [(s["pdf_name"], s["page"]) for s in result]
        assert ("paper1", 1) in pdf_pages
        assert ("paper1", 2) in pdf_pages

    def test_visual_evidence_types(self) -> None:
        """Image and table evidence should have correct type."""
        evidence = [
            {
                "evidence_id": "img1",
                "pdf_name": "paper",
                "page_idx": 3,
                "chunk_type": "image",
                "heading": "Figure 1",
                "text": "Architecture diagram",
                "score": 0.9,
            },
            {
                "evidence_id": "tbl1",
                "pdf_name": "paper",
                "page_idx": 4,
                "chunk_type": "table",
                "heading": "Table 1",
                "text": "Results comparison",
                "score": 0.85,
            },
        ]

        result = build_structured_provenance(evidence)

        assert len(result) == 2
        types = {s["type"] for s in result}
        assert "image" in types
        assert "table" in types

    def test_text_truncation(self) -> None:
        """Long text should be truncated in supporting_text."""
        long_text = "A" * 500
        evidence = [
            {
                "evidence_id": "id1",
                "pdf_name": "paper",
                "page_idx": 1,
                "chunk_type": "text",
                "heading": "Section",
                "text": long_text,
                "score": 0.9,
            }
        ]

        result = build_structured_provenance(evidence)

        assert len(result) == 1
        supporting = result[0]["supporting_text"]
        assert supporting is not None
        assert len(supporting) <= 203  # 200 + "..."
        assert supporting.endswith("...")

    def test_missing_optional_fields(self) -> None:
        """Evidence with missing optional fields should still work."""
        evidence = [
            {
                "pdf_name": "paper",
                "page_idx": 1,
                "chunk_type": "text",
                "text": "Some content",
            }
        ]

        result = build_structured_provenance(evidence)

        assert len(result) == 1
        source = result[0]
        assert source["chunk_id"] is None
        assert source["heading"] is None
        assert source["paper_version"] is None

    def test_invalid_page_idx_handled(self) -> None:
        """Invalid page_idx should be converted to 0."""
        evidence = [
            {
                "pdf_name": "paper",
                "page_idx": "invalid",
                "chunk_type": "text",
                "text": "Content",
            }
        ]

        result = build_structured_provenance(evidence)

        assert len(result) == 1
        assert result[0]["page"] == 0

    def test_none_page_idx_handled(self) -> None:
        """None page_idx should be converted to 0."""
        evidence = [
            {
                "pdf_name": "paper",
                "page_idx": None,
                "chunk_type": "text",
                "text": "Content",
            }
        ]

        result = build_structured_provenance(evidence)

        assert len(result) == 1
        assert result[0]["page"] == 0

    def test_missing_pdf_name_skipped(self) -> None:
        """Evidence without pdf_name should be skipped."""
        evidence = [
            {
                "page_idx": 1,
                "chunk_type": "text",
                "text": "Content",
            }
        ]

        result = build_structured_provenance(evidence)

        assert len(result) == 0

    def test_paper_version_field(self) -> None:
        """paper_version should be passed through when present."""
        evidence = [
            {
                "evidence_id": "id1",
                "pdf_name": "paper",
                "page_idx": 1,
                "chunk_type": "text",
                "text": "Content",
                "paper_version": 2,
            }
        ]

        result = build_structured_provenance(evidence)

        assert len(result) == 1
        assert result[0]["paper_version"] == 2


class TestSourceSchema:
    """Tests for SourceSchema with extended fields."""

    def test_backward_compatible_fields(self) -> None:
        """Schema should work with only required fields."""
        source = SourceSchema(pdf_name="paper", page=1, type="text")

        assert source.pdf_name == "paper"
        assert source.page == 1
        assert source.type == "text"
        assert source.chunk_id is None
        assert source.paper_version is None
        assert source.heading is None
        assert source.supporting_text is None

    def test_extended_fields(self) -> None:
        """Schema should accept all extended fields."""
        source = SourceSchema(
            pdf_name="paper",
            page=5,
            type="image",
            chunk_id="abc123",
            paper_version=2,
            heading="Figure 1",
            supporting_text="Architecture diagram",
        )

        assert source.pdf_name == "paper"
        assert source.page == 5
        assert source.type == "image"
        assert source.chunk_id == "abc123"
        assert source.paper_version == 2
        assert source.heading == "Figure 1"
        assert source.supporting_text == "Architecture diagram"

    def test_model_dump_includes_all_fields(self) -> None:
        """model_dump should include all fields."""
        source = SourceSchema(
            pdf_name="paper",
            page=1,
            type="text",
            chunk_id="id123",
            heading="Section",
        )

        data = source.model_dump()

        assert data["pdf_name"] == "paper"
        assert data["page"] == 1
        assert data["type"] == "text"
        assert data["chunk_id"] == "id123"
        assert data["heading"] == "Section"
        assert "paper_version" in data
        assert "supporting_text" in data

    def test_model_dump_exclude_none(self) -> None:
        """model_dump with exclude_none should omit None fields."""
        source = SourceSchema(pdf_name="paper", page=1, type="text")

        data = source.model_dump(exclude_none=True)

        assert "chunk_id" not in data
        assert "paper_version" not in data
        assert "heading" not in data
        assert "supporting_text" not in data
