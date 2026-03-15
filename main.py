import argparse
from src.ingest.mineru_parser import MinerUParser
from src.rag.vector_store import PaperVectorStore
from src.agent.graph import app as agent_app
from langchain_core.messages import HumanMessage
from src.utils.logger import get_logger

logger = get_logger(__name__)

def add_paper(pdf_path: str):
    logger.info(f"Adding paper from {pdf_path}...")
    
    # 1. Parse
    parser = MinerUParser(output_dir="./data/parsed")
    parsed_data = parser.parse_pdf(pdf_path)
    
    # 2. Chunk (Granular based on element types)
    chunks_data, doc_metadata = parser.chunk_content(parsed_data)
    
    # Save the cleaned chunks back as a reconstructed markdown for easier reading (optional)
    clean_md_path = f"{parser.output_dir}/{parsed_data.get('pdf_name')}/{parsed_data.get('pdf_name')}_clean.md"
    try:
        import os
        with open(clean_md_path, "w", encoding="utf-8") as f:
            for chunk in chunks_data:
                f.write(chunk["content"] + "\n\n")
    except Exception as e:
        logger.error(f"Could not save markdown: {e}")

    # 3. Store
    store = PaperVectorStore()
    
    # Extract structural chunks and enrich with file metadata
    multimodal_inputs = []
    metadata_list = []
    
    for chunk in chunks_data:
        # Merge file metadata with chunk-level layout metadata
        meta = {
            "title": doc_metadata.get("title_extracted") or parsed_data.get("title", "Unknown Title"),
            "pdf_name": parsed_data.get("pdf_name", ""),
            "chunk_type": chunk.get("type", "text"),
            "authors": " | ".join(doc_metadata.get("pre_abstract_meta", [])[:5]), # Quick heuristic
            "footnotes_count": len(doc_metadata.get("footnotes_and_discarded", []))
        }
        meta.update(chunk.get("metadata", {}))
        
        # Build multimodal input dict for Qwen3-VL
        input_item = {"text": chunk["content"]}
        
        images_to_embed = []
        
        # If the chunk has a primary image path (e.g. from an image or table block)
        if meta.get("img_path"):
            import os
            # Build absolute path taking MinerU output_dir structure into account
            # MinerU puts it under output_dir/pdf_name/img_path
            img_abs_path = os.path.join(parser.output_dir, meta["pdf_name"], meta["img_path"])
            if os.path.exists(img_abs_path):
                images_to_embed.append(img_abs_path)
                
        # Update equation image paths to absolute paths in metadata for later UI/user reference,
        # but DO NOT add them to images_to_embed so they aren't processed by the Vision Model.
        if meta.get("equation_imgs"):
            import os
            abs_eq_imgs = []
            for eq_img in meta["equation_imgs"]:
                eq_abs_path = os.path.join(parser.output_dir, meta["pdf_name"], eq_img)
                if os.path.exists(eq_abs_path):
                    abs_eq_imgs.append(eq_abs_path)
            # Replace relative paths in metadata with absolute ones for easy local access
            meta["equation_imgs"] = abs_eq_imgs
                    
        if images_to_embed:
            # Qwen3VLEmbedder supports a single string or a list of strings
            input_item["image"] = images_to_embed if len(images_to_embed) > 1 else images_to_embed[0]
                
        multimodal_inputs.append(input_item)
        metadata_list.append(meta)
        
    # Use store_multimodal_inputs to embed text and images simultaneously
    store.store_multimodal_inputs(multimodal_inputs, metadata_list)
    logger.info("Paper added successfully!")

def query_agent(question: str):
    logger.info(f"Question: {question}")
    
    inputs = {
        "messages": [HumanMessage(content=question)],
        "intermediate_steps": [],
        "current_plan": "",
        "documents": []
    }
    
    # stream events to console
    for event in agent_app.stream(inputs, stream_mode="values"):
        message = event.get("messages")
        if message:
            logger.info(f"Agent Action/Response: {message[-1].content}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agentic RAG System for Research Papers")
    subparsers = parser.add_subparsers(dest="command")
    
    # Add paper command
    parser_add = subparsers.add_parser("add")
    parser_add.add_argument("pdf_path", type=str, help="Path to the PDF file")
    
    # Query command
    parser_query = subparsers.add_parser("query")
    parser_query.add_argument("question", type=str, help="Question to ask the agent")
    
    args = parser.parse_args()
    
    if args.command == "add":
        add_paper(args.pdf_path)
    elif args.command == "query":
        query_agent(args.question)
    else:
        parser.print_help()