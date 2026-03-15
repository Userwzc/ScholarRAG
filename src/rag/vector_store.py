from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, models
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document

class PaperVectorStore:
    def __init__(self, host: str = "localhost", port: int = 6333, collection_name: str = "papers_rag"):
        # For simplicity and out-of-the-box execution, we use an in-memory client. 
        # Change to `url=f"http://{host}:{port}"` if you have a Qdrant docker container running.
        from config.settings import config
        self.client = QdrantClient(url=f"http://{config.QDRANT_HOST}:{config.QDRANT_PORT}")
        self.collection_name = collection_name
        
        # Configure embedding model. We assume the OpenAI-like endpoint provides text-embedding-ada-002 compatible outputs.
        # Or an open-source embedding model deployed locally (bge-large, m3, etc).
        from config.settings import config
        self.embeddings = OpenAIEmbeddings(
            openai_api_base=config.OPENAI_API_BASE,
            openai_api_key=config.OPENAI_API_KEY,
            model=config.EMBEDDING_MODEL
        )
        
        self._ensure_collection()
    
    def _ensure_collection(self, vector_size: int = 1536):
        """Create Qdrant collection if not exists"""
        collections = self.client.get_collections()
        if not any(col.name == self.collection_name for col in collections.collections):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
            )
            print(f"Created Qdrant collection: {self.collection_name}")
            
    def store_paper_chunks(self, chunks: List[str], metadata: Dict[str, Any]):
        """Embeds and uploads chunks to Qdrant collection"""
        docs = [
            Document(page_content=chunk, metadata=metadata)
            for chunk in chunks
        ]
        
        from config.settings import config
        # Insert using safer instantiation instead of class method from_documents kwargs unpacking bug
        qdrant = QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=self.embeddings,
        )
        qdrant.add_documents(documents=docs)
        print(f"Stored {len(chunks)} chunks in collection {self.collection_name}.")
        
    def search_similar(self, query: str, top_k: int = 5, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Document]:
        """Performs vector search on the collection"""
        qdrant_store = QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=self.embeddings
        )
        filter_params = None
        if filter_metadata:
            # Simple exact-match filter mapping building
            conditions = []
            for key, val in filter_metadata.items():
                conditions.append(models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=val)
                ))
            if conditions:
                filter_params = models.Filter(must=conditions)
        
        return qdrant_store.similarity_search(query, k=top_k, filter=filter_params)
