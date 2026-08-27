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
PIPER_VOICE = os.getenv("PIPER_VOICE", str(VOICES_DIR / "en_US-lessac-medium.onnx"))
