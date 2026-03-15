from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, models
from .embedding import Qwen3VLEmbeddings
from src.utils.logger import get_logger

logger = get_logger(__name__)

class PaperVectorStore:
    def __init__(self, host: str = "localhost", port: int = 6333, collection_name: str = "papers_rag"):
        # For simplicity and out-of-the-box execution, we use an in-memory client. 
        # Change to `url=f"http://{host}:{port}"` if you have a Qdrant docker container running.
        from config.settings import config
        self.client = QdrantClient(url=f"http://{config.QDRANT_HOST}:{config.QDRANT_PORT}")
        self.collection_name = collection_name
        
        # Configure embedding model using the Qwen3-VL embedder.
        from config.settings import config
        self.embeddings = Qwen3VLEmbeddings(
            model_name_or_path=config.EMBEDDING_MODEL
        )
        
        self._ensure_collection()
    
    def _ensure_collection(self, vector_size: int = None):
        """Create Qdrant collection if not exists"""
        if vector_size is None:
            # Dynamically determine the vector size from the model
            vector_size = len(self.embeddings.embed_query("test"))
            
        collections = self.client.get_collections()
        if not any(col.name == self.collection_name for col in collections.collections):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
            )
            logger.info(f"Created Qdrant collection: {self.collection_name}")
            
    def store_paper_chunks(self, chunks: List[str], metadatas: List[Dict[str, Any]]):
        """Embeds and uploads chunks to Qdrant collection"""
        import uuid
        
        vectors = self.embeddings.embed_documents(chunks)
        
        points = []
        for chunk, vector, metadata in zip(chunks, vectors, metadatas):
            payload = {**metadata, "page_content": chunk}
            points.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=payload
                )
            )
            
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        logger.info(f"Stored {len(chunks)} chunks in collection {self.collection_name}.")
        
    def search_similar(self, query: str, top_k: int = 5, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Performs vector search on the collection"""
        vector = self.embeddings.embed_query(query)
        
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
        
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            limit=top_k,
            query_filter=filter_params
        )
        
        formatted_results = []
        for res in results:
            formatted_results.append({
                "score": res.score,
                "payload": res.payload
            })
            
        return formatted_results

    def store_multimodal_inputs(self, inputs: List[Dict[str, Any]], metadatas: List[Dict[str, Any]] = None, batch_size: int = 4):
        """
        Embeds and uploads multimodal inputs (text + images) to Qdrant collection directly via QdrantClient.
        This bypasses LangChain's strict string content requirement.
        """
        import uuid
        if metadatas is None:
            metadatas = [{} for _ in range(len(inputs))]
            
        if len(inputs) != len(metadatas):
            raise ValueError("Number of inputs must match number of metadatas")

        # Process embeddings in batches directly
        points = []
        for i in range(0, len(inputs), batch_size):
            batch_inputs = inputs[i:i + batch_size]
            batch_metadatas = metadatas[i:i + batch_size]
            
            # This calls model.process() which we have now also patched to handle memory better
            vectors = self.embeddings.embed_inputs(batch_inputs)
            
            for j, (vector, metadata) in enumerate(zip(vectors, batch_metadatas)):
                original_idx = i + j
                payload = {**metadata, "_multimodal_input": inputs[original_idx]}
                points.append(
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload=payload
                    )
                )
            
            # Upsert the batch
            self.client.upsert(
                collection_name=self.collection_name,
                points=points[-len(batch_inputs):]
            )
            logger.info(f"Upserted batch {i//batch_size + 1}, {len(batch_inputs)} items...")
            
        logger.info(f"Stored {len(inputs)} multimodal items in collection {self.collection_name}.")

    def search_by_image(self, image_path: str, instruction: str = None, text: str = None, top_k: int = 5, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search the collection using an image, with optional text and instructions.
        Returns the parsed Qdrant payload directly instead of LangChain documents.
        """
        vector = self.embeddings.embed_image(image_path=image_path, text=text, instruction=instruction)
        
        filter_params = None
        if filter_metadata:
            conditions = []
            for key, val in filter_metadata.items():
                conditions.append(models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=val)
                ))
            if conditions:
                filter_params = models.Filter(must=conditions)
                
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            limit=top_k,
            query_filter=filter_params
        )
        
        # Format results to look a bit like LangChain documents, but as dicts
        formatted_results = []
        for res in results:
            formatted_results.append({
                "score": res.score,
                "payload": res.payload
            })
            
        return formatted_results
