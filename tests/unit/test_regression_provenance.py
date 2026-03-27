"""
Regression tests for provenance schema persistence in messages.

These tests verify:
- Provenance schema persistence in messages
- Structured sources in query responses
- Citation coverage validation
"""

import json

import pytest

from api.schemas import SourceSchema
from src.agent.evidence_builder import build_structured_provenance


# ============================================================================
# Provenance Schema Tests
# ============================================================================


class TestProvenanceSchema:
    """Tests for provenance schema validation."""

    def test_source_schema_required_fields(self) -> None:
        """SourceSchema should require pdf_name, page, and type."""
        source = SourceSchema(
            pdf_name="test_paper",
            page=5,
            type="text",
        )

        assert source.pdf_name == "test_paper"
        assert source.page == 5
        assert source.type == "text"

    def test_source_schema_optional_fields(self) -> None:
        """SourceSchema should accept optional provenance fields."""
        source = SourceSchema(
            pdf_name="test_paper",
            page=5,
            type="image",
            chunk_id="chunk-abc123",
            paper_version=2,
            heading="Figure 1",
            supporting_text="Architecture diagram",
        )

        assert source.chunk_id == "chunk-abc123"
        assert source.paper_version == 2
        assert source.heading == "Figure 1"
        assert source.supporting_text == "Architecture diagram"

    def test_source_schema_serialization(self) -> None:
        """SourceSchema should serialize to dict correctly."""
        source = SourceSchema(
            pdf_name="test_paper",
            page=5,
            type="text",
            chunk_id="id123",
            paper_version=1,
        )

        data = source.model_dump()

        assert data["pdf_name"] == "test_paper"
        assert data["page"] == 5
        assert data["type"] == "text"
        assert data["chunk_id"] == "id123"
        assert data["paper_version"] == 1

    def test_source_schema_exclude_none(self) -> None:
        """SourceSchema should exclude None fields when requested."""
        source = SourceSchema(
            pdf_name="test_paper",
            page=5,
            type="text",
        )

        data = source.model_dump(exclude_none=True)

        assert "pdf_name" in data
        assert "page" in data
        assert "type" in data
        assert "chunk_id" not in data
        assert "paper_version" not in data


# ============================================================================
# Provenance Building Tests
# ============================================================================


class TestBuildStructuredProvenance:
    """Tests for build_structured_provenance function."""

    def test_empty_evidence_returns_empty_list(self) -> None:
        """Empty evidence should return empty provenance list."""
        result = build_structured_provenance([])
        assert result == []

    def test_single_evidence_produces_provenance(self) -> None:
        """Single evidence should produce valid provenance."""
        evidence = [
            {
                "evidence_id": "chunk-123",
                "pdf_name": "test_paper",
                "page_idx": 5,
                "chunk_type": "text",
                "heading": "Introduction",
                "text": "This is the introduction section.",
                "paper_version": 1,
            }
        ]

        result = build_structured_provenance(evidence)

        assert len(result) == 1
        source = result[0]
        assert source["pdf_name"] == "test_paper"
        assert source["page"] == 5
        assert source["type"] == "text"
        assert source["chunk_id"] == "chunk-123"
        assert source["heading"] == "Introduction"
        assert source["paper_version"] == 1

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
            },
            {
                "evidence_id": "id2",
                "pdf_name": "paper1",
                "page_idx": 1,
                "chunk_type": "text",
                "heading": "Section B",
                "text": "Content B",
            },
            {
                "evidence_id": "id3",
                "pdf_name": "paper1",
                "page_idx": 2,
                "chunk_type": "text",
                "heading": "Section C",
                "text": "Content C",
            },
        ]

        result = build_structured_provenance(evidence)

        # Should deduplicate to 2 unique (pdf_name, page) pairs
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
            },
            {
                "evidence_id": "tbl1",
                "pdf_name": "paper",
                "page_idx": 4,
                "chunk_type": "table",
                "heading": "Table 1",
                "text": "Results comparison",
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
            }
        ]

        result = build_structured_provenance(evidence)

        assert len(result) == 1
        supporting = result[0]["supporting_text"]
        assert supporting is not None
        assert len(supporting) <= 203  # 200 + "..."
        assert supporting.endswith("...")

    def test_missing_optional_fields_handled(self) -> None:
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

    def test_invalid_page_idx_converted_to_zero(self) -> None:
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

    def test_none_page_idx_converted_to_zero(self) -> None:
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


# ============================================================================
# Citation Coverage Tests
# ============================================================================


class TestCitationCoverage:
    """Tests for citation coverage validation."""

    def test_valid_citation_coverage(self) -> None:
        """Valid citation should have required fields."""
        from tests.evaluation.metrics import check_citation_coverage

        chunk = {
            "metadata": {
                "pdf_name": "test_paper",
                "page": 1,
                "type": "text",
            }
        }

        assert check_citation_coverage(chunk) is True

    def test_missing_pdf_name_fails(self) -> None:
        """Missing pdf_name should fail citation coverage."""
        from tests.evaluation.metrics import check_citation_coverage

        chunk = {
            "metadata": {
                "page": 1,
                "type": "text",
            }
        }

        assert check_citation_coverage(chunk) is False

    def test_empty_pdf_name_fails(self) -> None:
        """Empty pdf_name should fail citation coverage."""
        from tests.evaluation.metrics import check_citation_coverage

        chunk = {
            "metadata": {
                "pdf_name": "",
                "page": 1,
                "type": "text",
            }
        }

        assert check_citation_coverage(chunk) is False

    def test_missing_page_fails(self) -> None:
        """Missing page should fail citation coverage."""
        from tests.evaluation.metrics import check_citation_coverage

        chunk = {
            "metadata": {
                "pdf_name": "test_paper",
                "type": "text",
            }
        }

        assert check_citation_coverage(chunk) is False


# ============================================================================
# Provenance Persistence Tests
# ============================================================================


class TestProvenancePersistence:
    """Tests for provenance persistence in messages."""

    @pytest.mark.asyncio
    async def test_provenance_in_message_response(
        self,
        temp_db,
    ) -> None:
        """Message response should include structured provenance."""
        from api.services import conversation_service
        from api.services.conversation_service import MessageCreate

        async with temp_db["session_maker"]() as session:
            # Create conversation
            conv = await conversation_service.create_conversation(
                session,
                conversation_id="test-conv-1",
                title="Test Conversation",
            )
            await session.commit()

            # Add assistant message with sources
            sources = [
                SourceSchema(
                    pdf_name="test_paper",
                    page=5,
                    type="text",
                    chunk_id="chunk-123",
                    paper_version=1,
                    heading="Introduction",
                )
            ]

            message = MessageCreate(
                id="msg-test-1",
                role="assistant",
                content="This is the answer.",
                sources=sources,
                created_at=1234567890,
            )

            await conversation_service.add_message(session, conv.id, message)
            await session.commit()

            # Retrieve messages
            conversation = await conversation_service.get_conversation(session, conv.id)
            messages = conversation.messages
            assert len(messages) == 1

            # Verify sources persisted
            saved_msg = messages[0]
            assert saved_msg.sources is not None
            sources_list = json.loads(saved_msg.sources)
            assert len(sources_list) == 1
            assert sources_list[0]["pdf_name"] == "test_paper"
            assert sources_list[0]["page"] == 5
            assert sources_list[0]["chunk_id"] == "chunk-123"

    @pytest.mark.asyncio
    async def test_provenance_with_version_info(
        self,
        temp_db,
    ) -> None:
        """Provenance should include version information."""
        from api.services import conversation_service
        from api.services.conversation_service import MessageCreate

        async with temp_db["session_maker"]() as session:
            conv = await conversation_service.create_conversation(
                session,
                conversation_id="test-conv-version",
                title="Test Conversation",
            )
            await session.commit()

            sources = [
                SourceSchema(
                    pdf_name="versioned_paper",
                    page=3,
                    type="image",
                    paper_version=2,
                    heading="Figure 1",
                )
            ]

            message = MessageCreate(
                id="msg-version-test",
                role="assistant",
                content="See Figure 1.",
                sources=sources,
                created_at=1234567890,
            )

            await conversation_service.add_message(session, conv.id, message)
            await session.commit()

            conversation = await conversation_service.get_conversation(session, conv.id)
            messages = conversation.messages
            sources_list = json.loads(messages[0].sources)
            assert sources_list[0]["paper_version"] == 2

    @pytest.mark.asyncio
    async def test_empty_sources_handled(
        self,
        temp_db,
    ) -> None:
        """Empty sources should be handled gracefully."""
        from api.services import conversation_service
        from api.services.conversation_service import MessageCreate

        async with temp_db["session_maker"]() as session:
            conv = await conversation_service.create_conversation(
                session,
                conversation_id="test-conv-empty",
                title="Test Conversation",
            )
            await session.commit()

            message = MessageCreate(
                id="msg-empty-sources",
                role="assistant",
                content="No relevant sources found.",
                sources=[],
                created_at=1234567890,
            )

            await conversation_service.add_message(session, conv.id, message)
            await session.commit()

            conversation = await conversation_service.get_conversation(session, conv.id)
            messages = conversation.messages
            assert messages[0].sources is None


# ============================================================================
# Provenance Field Validation Tests
# ============================================================================


class TestProvenanceFieldValidation:
    """Tests for provenance field validation."""

    def test_all_chunk_types_supported(self) -> None:
        """All chunk types should be supported in provenance."""
        chunk_types = ["text", "image", "table", "title", "footnote"]

        for chunk_type in chunk_types:
            evidence = [
                {
                    "pdf_name": "paper",
                    "page_idx": 1,
                    "chunk_type": chunk_type,
                    "text": "Content",
                }
            ]

            result = build_structured_provenance(evidence)
            assert len(result) == 1
            assert result[0]["type"] == chunk_type

    def test_provenance_with_special_characters(self) -> None:
        """Provenance should handle special characters in fields."""
        evidence = [
            {
                "evidence_id": "chunk-special",
                "pdf_name": "paper-with-dashes_and_underscores",
                "page_idx": 1,
                "chunk_type": "text",
                "heading": "Section with 'quotes' and \"double quotes\"",
                "text": "Content with special chars: @#$%^&*()",
            }
        ]

        result = build_structured_provenance(evidence)

        assert len(result) == 1
        assert result[0]["pdf_name"] == "paper-with-dashes_and_underscores"
        assert "quotes" in result[0]["heading"]

    def test_provenance_with_unicode(self) -> None:
        """Provenance should handle unicode characters."""
        evidence = [
            {
                "evidence_id": "chunk-unicode",
                "pdf_name": "论文_paper",
                "page_idx": 1,
                "chunk_type": "text",
                "heading": "章节 标题",
                "text": "中文内容 with English",
            }
        ]

        result = build_structured_provenance(evidence)

        assert len(result) == 1
        assert result[0]["pdf_name"] == "论文_paper"
        assert result[0]["heading"] == "章节 标题"
