import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_UPLOAD_DIR = os.getenv("API_UPLOAD_DIR", "./data/uploads")

DATABASE_PATH = os.getenv(
    "DATABASE_PATH", str(Path(__file__).parent.parent / "data" / "conversations.db")
)
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"
