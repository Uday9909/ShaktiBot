"""FastAPI service exposing the Shakti pipeline over HTTP.

Run:  uvicorn server:app --host 0.0.0.0 --port 8000
Single worker only — whisper/piper model caches are per-process.
"""
import asyncio
import base64
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import QdrantClient

from src import cache, config, llm, rag, stt, tts
from src.ingest import find_pdfs, ingest_document
from src.vectorstore import get_collection

app = FastAPI(title="Shakti Bot API")

app.add_middleware(
    CORSMiddleware,
    # Streamlit picks a free port (8501, 8502, …) — allow any localhost origin.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


def _transcribe(audio: bytes) -> str:
    """Transcribe raw WAV bytes (stt.transcribe needs a file path)."""
    fd, path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        return stt.transcribe(path)
    finally:
        os.unlink(path)


def _resolve_voice(voice):
    """Turn a voice name from /voices into a real onnx path (fall back to default)."""
    if not voice:
        return None
    p = Path(voice)
    if not p.is_absolute():
        p = config.VOICES_DIR / voice
    return str(p) if p.exists() else None


@app.get("/health")
async def health():
    redis_up = False
    try:
        redis_up = bool(cache._client.ping())
    except Exception:
        pass
    qdrant_up = False
    try:
        qdrant_up = bool(QdrantClient(url=config.QDRANT_URL, timeout=1).get_collections())
    except Exception:
        pass
    return {
        "status": "ok",
        "model": config.LLM_MODEL,
        "vector_db": "qdrant" if qdrant_up else f"{config.VECTOR_BACKEND} (down)",
        "redis": "up" if redis_up else "down",
    }


@app.get("/voices")
async def voices():
    return {"voices": sorted(p.name for p in config.VOICES_DIR.glob("*.onnx"))}


def _run_ingest():
    collection = get_collection()
    total_stored = total_skipped = 0
    for pdf in find_pdfs():
        _, stored, skipped = ingest_document(pdf, collection)
        total_stored += stored
        total_skipped += skipped
    return {"stored": total_stored, "skipped": total_skipped}


@app.post("/ingest")
async def ingest():
    return await asyncio.to_thread(_run_ingest)


async def _handle_chat(question: str, voice, debug: bool):
    chunks = None
    answer, src = await asyncio.to_thread(cache.get_answer, question, config.EMBED_MODEL)
    cached = src is not None
    if not cached:
        chunks = await asyncio.to_thread(rag.retrieve, question)
        answer = await llm.agenerate(question, chunks)
        await asyncio.to_thread(cache.put, question, answer, config.EMBED_MODEL)
    audio, audio_format = await asyncio.to_thread(
        tts.synthesize_with_format, answer, _resolve_voice(voice)
    )
    resp = {
        "answer": answer,
        "audio_wav_base64": base64.b64encode(audio).decode("ascii"),
        "audio_format": audio_format,
        "cached": cached,
    }
    if debug:
        resp["chunks"] = chunks
    return resp


@app.post("/chat")
async def chat(request: Request):
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("application/json"):
        payload = await request.json()
        question, voice, debug = payload.get("question"), payload.get("voice"), bool(payload.get("debug", False))
    else:
        form = await request.form()
        question, voice = None, form.get("voice")
        debug = (form.get("debug") or "").lower() == "true"
        f = form.get("audio_wav")
        if f is not None:
            question = await asyncio.to_thread(_transcribe, await f.read())
    if not question or not question.strip():
        raise HTTPException(status_code=422, detail="Provide a non-empty question or audio_wav.")
    return await _handle_chat(" ".join(question.split()), voice, debug)
