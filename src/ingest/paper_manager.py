import os
import shutil
from typing import Optional

from src.rag.vector_store import vector_store
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PaperManager:
    """Handles paper lifecycle operations: add, delete, list, etc."""

    def __init__(self, output_dir: str = "./data/parsed"):
        self.output_dir = output_dir

    def delete_paper(
        self, pdf_name: str, parsed_output_dir: Optional[str] = None
    ) -> bool:
        """Delete a paper from Qdrant and optionally remove its parsed files.

        Args:
            pdf_name: Name of the PDF (without extension)
            parsed_output_dir: Path to parsed files directory. Defaults to output_dir.

        Returns:
            True if deletion was successful, False otherwise.
        """
        success = vector_store.delete_paper(pdf_name)

        if not success:
            logger.error("Failed to delete paper '%s' from vector store.", pdf_name)
            return False

        target_dir = parsed_output_dir or self.output_dir
        parsed_dir = os.path.join(target_dir, pdf_name)
        if os.path.isdir(parsed_dir):
            shutil.rmtree(parsed_dir)
            logger.info("Removed parsed files: %s", parsed_dir)
        else:
            logger.warning("No parsed files found for: %s", pdf_name)

        logger.info("Paper '%s' deleted successfully.", pdf_name)
        return True
