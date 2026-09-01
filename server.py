"""FastAPI service exposing the Shakti pipeline over HTTP.

Run:  uvicorn server:app --host 0.0.0.0 --port 8000
Single worker only — whisper/piper model caches are per-process.
"""
import asyncio
import base64
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient

from src import cache, config, llm, rag, stt, tts
from src.ingest import find_pdfs, ingest_document
from src.vectorstore import get_collection

app = FastAPI(title="Shakti Bot API")
logger = logging.getLogger("shakti.api")
_rate_limit: dict[str, list[float]] = {}


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed request_id=%s path=%s", request_id, request.url.path)
        raise
    elapsed = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info("request_complete request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
                request_id, request.method, request.url.path, response.status_code, elapsed)
    return response


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=config.MAX_QUESTION_LENGTH)
    voice: str | None = None
    debug: bool = False
    category: str | None = Field(default=None, pattern=r"^[a-z_]{2,40}$")
    persona: str = Field(default="visitor", pattern=r"^(student|parent|visitor)$")
    lang: str = Field(default="en", pattern=r"^(en|hi|mr)$")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _check_rate_limit(client_id: str) -> None:
    now = time.monotonic()
    recent = [stamp for stamp in _rate_limit.get(client_id, [])
              if now - stamp < config.RATE_LIMIT_WINDOW]
    if len(recent) >= config.RATE_LIMIT_REQUESTS:
        raise HTTPException(status_code=429, detail="Too many requests. Try again shortly.")
    recent.append(now)
    _rate_limit[client_id] = recent


def _transcribe(audio: bytes) -> str:
    """Transcribe raw WAV bytes (stt.transcribe needs a file path)."""
    fd, path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        return stt.transcribe(path)
    finally:
        os.unlink(path)


def _resolve_voice(voice, lang="en"):
    """Turn a voice name from /voices into a real onnx path (fall back to default)."""
    if lang == "en" and (not voice or voice.startswith("hi_IN-")):
        voice = Path(config.PIPER_VOICE).name
    elif lang in {"hi", "mr"} and (not voice or voice.startswith("en_")):
        voice = "hi_IN-priyamvada-medium.onnx"
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
        logger.exception("redis_health_check_failed")
    qdrant_up = False
    try:
        qdrant_up = bool(QdrantClient(url=config.QDRANT_URL, timeout=1).get_collections())
    except Exception:
        logger.exception("qdrant_health_check_failed")
    ready = redis_up and (qdrant_up or config.VECTOR_BACKEND == "chroma")
    if not ready:
        raise HTTPException(status_code=503, detail={
            "status": "not_ready",
            "redis": "up" if redis_up else "down",
            "vector_db": "qdrant" if qdrant_up else f"{config.VECTOR_BACKEND} (down)",
        })
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
    cache.clear()
    return {"stored": total_stored, "skipped": total_skipped}


@app.post("/ingest")
async def ingest():
    return await asyncio.to_thread(_run_ingest)


async def _handle_chat(question: str, voice, debug: bool, category=None,
                       persona="visitor", lang="en"):
    chunks = None
    answer, src = await asyncio.to_thread(
        cache.get_answer, question, config.EMBED_MODEL, category, persona, lang
    )
    cached = src is not None
    if not cached:
        chunks = await asyncio.to_thread(rag.retrieve, question, None, None, category)
        answer = await llm.agenerate(question, chunks, persona=persona, lang=lang)
        await asyncio.to_thread(
            cache.put, question, answer, config.EMBED_MODEL, category, persona, lang
        )
    audio, audio_format = await asyncio.to_thread(
        tts.synthesize_with_format, answer, _resolve_voice(voice, lang), lang
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
    _check_rate_limit(request.client.host if request.client else "unknown")
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("application/json"):
        payload = ChatRequest.model_validate(await request.json())
        question = payload.question
        voice, debug = payload.voice, payload.debug
        category, persona, lang = payload.category, payload.persona, payload.lang
    else:
        form = await request.form()
        question, voice = None, form.get("voice")
        debug = (form.get("debug") or "").lower() == "true"
        f = form.get("audio_wav")
        if f is not None:
            if len(await f.read(config.MAX_AUDIO_BYTES + 1)) > config.MAX_AUDIO_BYTES:
                raise HTTPException(status_code=413, detail="audio_wav exceeds the 10 MB limit.")
            await f.seek(0)
            question = await asyncio.to_thread(_transcribe, await f.read())
        category = form.get("category")
        persona = form.get("persona") or "visitor"
        lang = form.get("lang") or "en"
    if not question or not question.strip():
        raise HTTPException(status_code=422, detail="Provide a non-empty question or audio_wav.")
    question = " ".join(question.split())
    if len(question) > config.MAX_QUESTION_LENGTH:
        raise HTTPException(status_code=422, detail="question is too long.")
    if persona not in llm.PERSONA_PROMPTS or lang not in {"en", "hi", "mr"}:
        raise HTTPException(status_code=422, detail="Unsupported persona or language.")
    return await _handle_chat(question, voice, debug, category, persona, lang)


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """Stream pipeline states and sentence audio for an animated client."""
    await websocket.accept()
    try:
        _check_rate_limit(websocket.client.host if websocket.client else "unknown")
        payload = ChatRequest.model_validate(await websocket.receive_json())
        await websocket.send_json({"type": "state", "state": "listening"})
        await websocket.send_json({"type": "state", "state": "searching"})
        answer, source = await asyncio.to_thread(
            cache.get_answer, payload.question, config.EMBED_MODEL, payload.category,
            payload.persona, payload.lang
        )
        cached = source is not None
        chunks = None
        if not cached:
            chunks = await asyncio.to_thread(
                rag.retrieve, payload.question, None, None, payload.category
            )
            await websocket.send_json({"type": "state", "state": "thinking"})
            answer = await llm.agenerate(
                payload.question, chunks, persona=payload.persona, lang=payload.lang
            )
            await asyncio.to_thread(
                cache.put, payload.question, answer, config.EMBED_MODEL, payload.category,
                payload.persona, payload.lang
            )
        await websocket.send_json({"type": "state", "state": "speaking", "text": answer})
        for audio, audio_format in await asyncio.to_thread(
            lambda: list(tts.synthesize_sentences(
                answer, _resolve_voice(payload.voice, payload.lang), payload.lang
            ))
        ):
            await websocket.send_json({
                "type": "audio",
                "audio_base64": base64.b64encode(audio).decode("ascii"),
                "audio_format": audio_format,
            })
        await websocket.send_json({"type": "complete", "answer": answer, "cached": cached,
                                   "chunks": chunks})
        await websocket.send_json({"type": "state", "state": "idle"})
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except HTTPException as exc:
        await websocket.send_json({"type": "error", "detail": exc.detail})
        await websocket.close(code=1008)
