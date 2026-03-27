"""
Sample paper data for testing.

This module provides deterministic sample data that can be used
across all tests without requiring real PDF parsing or model inference.
"""

from typing import Any

# Sample paper metadata for testing
SAMPLE_PAPERS: list[dict[str, Any]] = [
    {
        "pdf_name": "dream_paper",
        "title": "DREAM: Diffusion Rectification and Estimation for Adaptive Models",
        "authors": "Alice Researcher, Bob Scientist",
        "abstract": "We present DREAM, a novel framework for adaptive machine learning models.",
        "keywords": ["diffusion", "adaptive", "machine learning"],
        "total_pages": 12,
        "total_chunks": 45,
    },
    {
        "pdf_name": "attention_paper",
        "title": "Attention Is All You Need",
        "authors": "Vaswani et al.",
        "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
        "keywords": ["attention", "transformer", "neural network"],
        "total_pages": 15,
        "total_chunks": 52,
    },
    {
        "pdf_name": "bert_paper",
        "title": "BERT: Pre-training of Deep Bidirectional Transformers",
        "authors": "Devlin et al.",
        "abstract": "We introduce a new language representation model called BERT.",
        "keywords": ["bert", "transformer", "nlp"],
        "total_pages": 16,
        "total_chunks": 58,
    },
]

# Sample chunks for testing
SAMPLE_CHUNKS: list[dict[str, Any]] = [
    {
        "id": "chunk-1",
        "pdf_name": "dream_paper",
        "page_idx": 0,
        "chunk_type": "text",
        "heading": "Abstract",
        "content": "We present DREAM, a novel framework for adaptive machine learning models that achieves state-of-the-art results on multiple benchmarks.",
    },
    {
        "id": "chunk-2",
        "pdf_name": "dream_paper",
        "page_idx": 1,
        "chunk_type": "text",
        "heading": "1. Introduction",
        "content": "Machine learning has become a fundamental tool in many applications. In this paper, we propose a new approach.",
    },
    {
        "id": "chunk-3",
        "pdf_name": "dream_paper",
        "page_idx": 2,
        "chunk_type": "text",
        "heading": "2. Methodology",
        "content": "Our methodology consists of three main components: data preprocessing, model architecture, and training procedure.",
    },
    {
        "id": "chunk-4",
        "pdf_name": "dream_paper",
        "page_idx": 2,
        "chunk_type": "image",
        "heading": "Figure 1",
        "content": "Architecture diagram of the DREAM model showing the main components.",
        "img_path": "images/fig1.png",
    },
    {
        "id": "chunk-5",
        "pdf_name": "dream_paper",
        "page_idx": 3,
        "chunk_type": "table",
        "heading": "Table 1",
        "content": "Comparison of accuracy metrics across different methods on benchmark datasets.",
    },
]

# Sample evaluation queries for testing
SAMPLE_EVAL_QUERIES: list[dict[str, Any]] = [
    {
        "question": "What is the core methodology of the DREAM paper?",
        "expected_pdf": "dream_paper",
        "expected_pages": [2, 3],
        "keywords": ["methodology", "approach", "framework"],
    },
    {
        "question": "How does the model handle multimodal inputs?",
        "expected_pdf": "dream_paper",
        "expected_pages": [2, 4],
        "keywords": ["multimodal", "input", "fusion"],
    },
    {
        "question": "What are the experimental results?",
        "expected_pdf": "dream_paper",
        "expected_pages": [3, 5],
        "keywords": ["results", "accuracy", "benchmark"],
    },
]


def get_sample_paper(pdf_name: str) -> dict[str, Any] | None:
    """Get a sample paper by name."""
    for paper in SAMPLE_PAPERS:
        if paper["pdf_name"] == pdf_name:
            return paper
    return None


def get_sample_chunks(pdf_name: str) -> list[dict[str, Any]]:
    """Get sample chunks for a paper."""
    return [c for c in SAMPLE_CHUNKS if c["pdf_name"] == pdf_name]
