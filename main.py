import argparse
from src.ingest.mineru_parser import MinerUParser
from src.rag.vector_store import PaperVectorStore
from src.agent.graph import app as agent_app
from langchain_core.messages import HumanMessage

def add_paper(pdf_path: str):
    print(f"Adding paper from {pdf_path}...")
    
    # 1. Parse
    parser = MinerUParser(output_dir="./data/parsed")
    parsed_data = parser.parse_pdf(pdf_path)
    
    # 2. Chunk (Granular based on element types)
    chunks_data = parser.chunk_content(parsed_data)
    
    # 3. Store
    store = PaperVectorStore()
    
    # Extract structural chunks and enrich with file metadata
    texts = []
    metadata_list = []
    
    for chunk in chunks_data:
        # Text to embed
        texts.append(chunk["content"])
        
        # Merge file metadata with chunk-level layout metadata
        meta = {
            "title": parsed_data.get("title", "Unknown Title"),
            "pdf_name": parsed_data.get("pdf_name", ""),
            "chunk_type": chunk.get("type", "text")
        }
        meta.update(chunk.get("metadata", {}))
        metadata_list.append(meta)
        
    # We alter store.store_paper_chunks API loosely here to accept text arrays
    # or just convert to Langchain Documents here:
    from langchain_core.documents import Document
    from langchain_qdrant import QdrantVectorStore
    
    docs = [Document(page_content=t, metadata=m) for t, m in zip(texts, metadata_list)]
    
    from config.settings import config
    
    # Instantiate without from_documents constructor pattern via direct object use
    qdrant = QdrantVectorStore(
        client=store.client,
        collection_name=store.collection_name,
        embedding=store.embeddings,
    )
    
    qdrant.add_documents(documents=docs)
    print(f"Stored {len(docs)} highly granuler structural chunks in Qdrant.")
    print("Paper added successfully!")

def query_agent(question: str):
    print(f"\nQuestion: {question}\n")
    
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
            print(f"Agent Action/Response: {message[-1].content}")

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