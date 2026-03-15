import json
from typing import Any, Dict

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config.settings import config
from src.rag.vector_store import vector_store
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PaperSearchInput(BaseModel):
    query: str = Field(
        description="The scientific question or semantic query to search for."
    )
    filter_metadata: str = Field(
        default="{}",
        description=(
            "Optional JSON-formatted string of key-value metadata filters "
            '(e.g. {"authors": "Hinton", "pdf_name": "DREAM"}).'
        ),
    )


@tool("paper_retriever", args_schema=PaperSearchInput)
def retrieve_papers(query: str, filter_metadata: str = "{}") -> str:
    """Search the academic paper vector database for chunks relevant to a scientific question.

    Use this tool whenever the user asks about paper content, methodology, results,
    figures, tables, or authors.  Call it multiple times with different queries to
    gather information for multi-part questions.  If no relevant results are found,
    say so — do not fabricate information.
    """
    metadata_dict: Dict[str, Any] | None = None
    try:
        parsed = json.loads(filter_metadata)
        if isinstance(parsed, dict) and parsed:
            metadata_dict = parsed
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not parse filter_metadata JSON, ignoring filter: %s", exc)

    try:
        results = vector_store.search_similar(
            query, top_k=config.RAG_TOP_K, filter_metadata=metadata_dict
        )
    except Exception as exc:
        logger.error("Vector store search failed: %s", exc)
        return "Search failed due to an internal error."

    if not results:
        return "No relevant papers found for the query."

    formatted_results = []
    for doc in results:
        score: float = doc.get("score", 0.0)
        payload = doc.get("payload", {})

        # store_multimodal_inputs stores content under "_multimodal_input";
        # store_paper_chunks stores it under "page_content".  Handle both.
        mm = payload.get("_multimodal_input")
        if mm is not None:
            chunk = mm.get("text", "")
            if not chunk and "image" in mm:
                chunk = f"[Image: {mm['image']}]"
        else:
            chunk = payload.get("page_content", "")

        # Surface the metadata fields most useful for citation and context.
        title = payload.get("title", "Unknown Title")
        pdf_name = payload.get("pdf_name", "")
        authors = payload.get("authors", "")
        page_idx = payload.get("page_idx", "")
        chunk_type = payload.get("chunk_type", "text")

        header_parts = [f"[Paper: {title}"]
        if pdf_name:
            header_parts.append(f"  File: {pdf_name}.pdf")
        if authors:
            header_parts.append(f"  Authors: {authors}")
        if page_idx != "":
            header_parts.append(f"  Page: {page_idx}")
        header_parts.append(f"  Type: {chunk_type}")
        header_parts.append(f"  Score: {score:.3f}]")

        formatted_results.append("\n".join(header_parts) + "\n" + chunk)

    return "\n\n---\n\n".join(formatted_results)
