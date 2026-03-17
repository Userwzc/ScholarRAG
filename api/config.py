import os
from dotenv import load_dotenv

load_dotenv(override=True)

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_UPLOAD_DIR = os.getenv("API_UPLOAD_DIR", "./data/uploads")
