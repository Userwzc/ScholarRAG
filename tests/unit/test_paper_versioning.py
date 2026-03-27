from typing import Any

from api.services import paper_service
from src.core import ingestion


class _StubParser:
    def __init__(self, output_dir: str, backend: str) -> None:
        self.output_dir = output_dir
        self.backend = backend

    @property
    def backend_subdir(self) -> str:
        return "auto"

    def parse_pdf(self, pdf_path: str) -> dict[str, Any]:
        return {
            "pdf_name": "versioned-paper",
            "title": "Versioned Paper",
        }

    def chunk_content(
        self, parsed_data: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return (
            [
                {
                    "content": "text chunk",
                    "type": "text",
                    "metadata": {
                        "page_idx": 0,
                        "heading": "Intro",
                    },
                }
            ],
            {
                "title_extracted": "Versioned Paper",
                "pre_abstract_meta": [],
                "footnotes_and_discarded": [],
                "references": [],
            },
        )


def test_process_paper_includes_version_metadata(monkeypatch) -> None:
    monkeypatch.setattr(ingestion, "MinerUParser", _StubParser)

    _, metadata_list, _ = ingestion.process_paper(
        "/tmp/versioned-paper.pdf",
        save_markdown=False,
        paper_version=3,
        is_current=False,
    )

    assert metadata_list[0]["paper_version"] == 3
    assert metadata_list[0]["is_current"] is False


def test_default_paper_queries_only_return_current_version(
    mock_vector_store,
    mock_paper_service_vector_store,
) -> None:
    _ = mock_paper_service_vector_store

    inputs = [
        {"text": "old version intro"},
        {"text": "current version intro"},
    ]
    metadatas = [
        {
            "pdf_name": "paper-a",
            "title": "Paper A",
            "authors": "Author",
            "chunk_type": "text",
            "heading": "Intro",
            "page_idx": 0,
            "paper_version": 1,
            "is_current": False,
        },
        {
            "pdf_name": "paper-a",
            "title": "Paper A",
            "authors": "Author",
            "chunk_type": "text",
            "heading": "Intro",
            "page_idx": 0,
            "paper_version": 2,
            "is_current": True,
        },
    ]
    mock_vector_store.add_multimodal(inputs, metadatas)

    papers = paper_service.list_papers()
    assert len(papers) == 1
    assert papers[0].chunk_count == 1
    assert papers[0].paper_version == 2

    detail = paper_service.get_paper_detail("paper-a")
    assert detail is not None
    assert detail.chunk_count == 1
    assert detail.paper_version == 2
    assert detail.is_current is True

    chunks = paper_service.get_paper_chunks("paper-a", page=1, limit=10)
    assert chunks.total == 1
    assert len(chunks.chunks) == 1
    assert chunks.chunks[0].paper_version == 2


def test_version_override_returns_historical_chunks_and_toc(
    mock_vector_store,
    mock_paper_service_vector_store,
) -> None:
    _ = mock_paper_service_vector_store

    mock_vector_store.add_multimodal(
        inputs=[
            {"text": "old version section"},
            {"text": "new version section"},
        ],
        metadatas=[
            {
                "pdf_name": "paper-b",
                "title": "Paper B",
                "authors": "Author",
                "chunk_type": "text",
                "heading": "Old Intro",
                "section_depth": 1,
                "page_idx": 0,
                "paper_version": 1,
                "is_current": False,
            },
            {
                "pdf_name": "paper-b",
                "title": "Paper B",
                "authors": "Author",
                "chunk_type": "text",
                "heading": "New Intro",
                "section_depth": 1,
                "page_idx": 0,
                "paper_version": 2,
                "is_current": True,
            },
        ],
    )

    historical_chunks = paper_service.get_paper_chunks(
        "paper-b",
        page=1,
        limit=10,
        version=1,
    )
    assert historical_chunks.total == 1
    assert historical_chunks.chunks[0].paper_version == 1
    assert historical_chunks.chunks[0].is_current is False

    historical_toc = paper_service.get_paper_toc("paper-b", version=1)
    assert historical_toc is not None
    assert len(historical_toc.items) == 1
    assert historical_toc.items[0].text == "Old Intro"

    current_toc = paper_service.get_paper_toc("paper-b")
    assert current_toc is not None
    assert len(current_toc.items) == 1
    assert current_toc.items[0].text == "New Intro"
