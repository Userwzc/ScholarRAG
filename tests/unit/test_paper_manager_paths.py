from config.settings import config
from src.ingest.paper_manager import PaperManager


def test_paper_manager_uses_configured_parsed_output_dir() -> None:
    manager = PaperManager()
    assert manager.output_dir == config.PARSED_OUTPUT_DIR
