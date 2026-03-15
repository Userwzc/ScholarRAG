# Config settings
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-xxxx")
    QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./metadata.db")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/Qwen3-VL-Embedding-2B") # 默认使用硅基流动上的bge-m3模型
    LLM_MODEL = os.getenv("LLM_MODEL", "Pro/moonshotai/Kimi-K2.5") # 默认使用Kimi-K2.5模型
    MINERU_MODEL_SOURCE = os.getenv("MINERU_MODEL_SOURCE", "modelscope") # 可选 local,modelscope,huggingface

config = Config()