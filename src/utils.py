"""Small shared helpers: Ollama client, embedding, text cleaning, hashing."""
import hashlib
import re

import ollama

from . import config


def get_client() -> ollama.Client:
    return ollama.Client(host=config.OLLAMA_HOST)


def aget_client() -> ollama.AsyncClient:
    return ollama.AsyncClient(host=config.OLLAMA_HOST)


def embed_text(text: str) -> list[float]:
    """Embed a single text with the configured Ollama embedding model."""
    resp = get_client().embed(model=config.EMBED_MODEL, input=text)
    return resp["embeddings"][0]


async def aembed_text(text: str) -> list[float]:
    """Async embed — call from async contexts so the event loop stays free."""
    resp = await aget_client().embed(model=config.EMBED_MODEL, input=text)
    return resp["embeddings"][0]


def clean_text(text: str) -> str:
    """Normalize extracted text: fix newlines, collapse spaces, keep paragraphs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def content_hash(text: str) -> str:
    """Deterministic id for a chunk — enables de-duplication on re-ingest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
