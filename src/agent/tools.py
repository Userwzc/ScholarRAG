from typing import List, Dict, Any, Type
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field
from src.rag.vector_store import PaperVectorStore
import json

# Vector store initialization
vector_store = PaperVectorStore()

class PaperSearchInput(BaseModel):
    query: str = Field(description="The scientific question or semantic query to search for.")
    filter_metadata: str = Field(
        default="{}", 
        description="Optional JSON-formatted string representing key-value metadata to filter (e.g. {\"author\": \"Hinton\"})"
    )

@tool("paper_retriever", args_schema=PaperSearchInput)
def retrieve_papers(query: str, filter_metadata: str = "{}") -> str:
    """Useful for answering semantic questions based on research paper contents mapping to vector embeddings."""
    try:
        metadata_dict = json.loads(filter_metadata)
    except:
        metadata_dict = None
        
    results = vector_store.search_similar(query, top_k=5, filter_metadata=metadata_dict)
    
    if not results:
        return "No relevant papers found for the query."
        
    formatted_results = []
    for doc in results:
        payload = doc.get("payload", {})
        metadata = {k: v for k, v in payload.items() if k != "page_content" and k != "_multimodal_input"}
        chunk = payload.get("page_content", "")
        # fallback for multimodal if page_content isn't there
        if not chunk and "_multimodal_input" in payload:
            chunk = payload["_multimodal_input"].get("text", "")
            if not chunk and "image" in payload["_multimodal_input"]:
                chunk = f"[Image: {payload['_multimodal_input']['image']}]"
                
        formatted = f"[Paper: {metadata.get('title', 'Unknown Title')}]\n{chunk}"
        formatted_results.append(formatted)
        
    return "\n\n---\n\n".join(formatted_results)

# Other tools like SQL tool would go here to search metadata (year, authors) robustly
