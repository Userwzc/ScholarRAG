"""
Test fixtures for ScholarRAG.

This package contains reusable test data and fixtures for:
- Sample PDFs for upload testing
- Mock data for vector store testing
- Evaluation datasets for regression testing
"""

from pathlib import Path

# Path to fixtures directory
FIXTURES_DIR = Path(__file__).parent

# Path to sample PDFs
PDF_FIXTURES_DIR = FIXTURES_DIR / "pdfs"
