from src.custom.qwen3_vl_embedding import Qwen3VLEmbedder

class Qwen3VLEmbeddings:
    def __init__(self, model_name_or_path: str = "../models/Qwen3-VL-Embedding-2B", **kwargs):
        self.model = Qwen3VLEmbedder(model_name_or_path=model_name_or_path, **kwargs)
        
    def embed_documents(self, texts: list[str], instruction: str = None) -> list[list[float]]:
        inputs = [{"text": text} for text in texts]
        if instruction:
            for item in inputs:
                item["instruction"] = instruction
        embeddings = self.model.process(inputs)
        return embeddings.tolist()
    
    def embed_query(self, text: str, instruction: str = "Retrieve images or text relevant to the user's query.") -> list[float]:
        inputs = [{"text": text, "instruction": instruction}]
        embeddings = self.model.process(inputs)
        return embeddings.tolist()[0]
    
    def embed_image(self, image_path: str, text: str = None, instruction: str = None) -> list[float]:
        input_data = {"image": image_path}
        if text:
            input_data["text"] = text
        if instruction:
            input_data["instruction"] = instruction
        embeddings = self.model.process([input_data])
        return embeddings.tolist()[0]
        
    def embed_images(self, image_paths: list[str], instruction: str = None) -> list[list[float]]:
        inputs = [{"image": path} for path in image_paths]
        if instruction:
            for item in inputs:
                item["instruction"] = instruction
        embeddings = self.model.process(inputs)
        return embeddings.tolist()
        
    def embed_inputs(self, inputs: list[dict]) -> list[list[float]]:
        """
        Embed a list of multimodal inputs directly, following the official Qwen3-VL-Embedding dict style.
        Each dict can contain: 'text', 'image', 'video', 'instruction'.
        """
        embeddings = self.model.process(inputs)
        return embeddings.tolist()