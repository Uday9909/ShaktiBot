"""Central configuration for Shakti Bot.

Every path and model choice lives here so components stay swappable.
Values can be overridden via a .env file or environment variables.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Project layout
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("SHAKTI_DATA_DIR", ROOT / "data"))
CHROMA_DIR = Path(os.getenv("SHAKTI_CHROMA_DIR", ROOT / "chroma_db"))
VOICES_DIR = Path(os.getenv("SHAKTI_VOICES_DIR", ROOT / "voices"))

load_dotenv(ROOT / ".env")

# Ollama
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3:4b-instruct-2507-q4_K_M")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

# Retrieval
COLLECTION = os.getenv("COLLECTION", "college_docs")
TOP_K = int(os.getenv("TOP_K", "4"))
CHUNK_WORDS = int(os.getenv("CHUNK_WORDS", "200"))

# Speech
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))

# TTS
PIPER_VOICE = os.getenv("PIPER_VOICE", str(VOICES_DIR / "hi_IN-priyamvada-medium.onnx"))

# Vector store backend: "chroma" or "qdrant"
VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "qdrant")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

# API service (server.py)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Streamlit UI: URL the browser must use to reach the API. Inside Docker the
# server-side calls need http://api:8000 but the wake-word JS (running in the
# user's browser) needs the host-visible URL.
BROWSER_API_BASE_URL = os.getenv("BROWSER_API_BASE_URL", API_BASE_URL)

# Streamlit result-relay listener (app.py). RELAY_PORT=0 picks a random free
# port (local dev); Docker pins it to 8502 and binds 0.0.0.0.
RELAY_HOST = os.getenv("RELAY_HOST", "127.0.0.1")
RELAY_PORT = int(os.getenv("RELAY_PORT", "0"))

# Redis semantic cache
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_THRESHOLD = float(os.getenv("CACHE_THRESHOLD", "0.93"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "86400"))

# Vector store backend: "chroma" or "qdrant"
VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "qdrant")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

# API service (server.py)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Redis semantic cache
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_THRESHOLD = float(os.getenv("CACHE_THRESHOLD", "0.93"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "86400"))

