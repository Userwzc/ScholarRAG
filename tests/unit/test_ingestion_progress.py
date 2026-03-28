from typing import Any

from src.core import ingestion


class _StubParser:
    last_output_dir: str = ""

    def __init__(self, output_dir: str, backend: str) -> None:
        self.output_dir = output_dir
        self.backend = backend
        _StubParser.last_output_dir = output_dir

    @property
    def backend_subdir(self) -> str:
        return "auto"

    def parse_pdf(self, pdf_path: str) -> dict[str, Any]:
        return {
            "pdf_name": "stub-paper",
            "title": "Stub Paper",
        }

    def chunk_content(self, parsed_data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return (
            [
                {
                    "content": "hello world",
                    "type": "text",
                    "metadata": {"page_idx": 0, "heading": "Intro"},
                }
            ],
            {
                "title_extracted": "Stub Paper",
                "pre_abstract_meta": [],
                "footnotes_and_discarded": [],
                "references": [],
            },
        )


def test_process_paper_reports_progress(monkeypatch) -> None:
    monkeypatch.setattr(ingestion, "MinerUParser", _StubParser)
    monkeypatch.setattr(ingestion.config, "PARSED_OUTPUT_DIR", "/tmp/test-parsed")

    stages: list[tuple[str, int]] = []

    def callback(stage: str, progress: int) -> None:
        stages.append((stage, progress))

    multimodal_inputs, metadata_list, parsed_data = ingestion.process_paper(
        "/tmp/stub-paper.pdf",
        save_markdown=False,
        progress_callback=callback,
    )

    assert parsed_data["pdf_name"] == "stub-paper"
    assert len(multimodal_inputs) == 1
    assert len(metadata_list) == 1
    assert stages == [
        ("parsing", 10),
        ("chunking", 35),
    ]
    assert _StubParser.last_output_dir == ingestion.config.PARSED_OUTPUT_DIR
