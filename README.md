# 🎓 Shakti Bot — Local Voice RAG Assistant

A college AI assistant that answers questions about clubs, policies, events, and
more — **entirely offline**. Speak a question (or type it), get a spoken answer
grounded in your own PDF documents.

Built for a **MacBook Air M2 / 8 GB RAM**. No cloud APIs, no large LLMs, no heavy
frameworks. Everything runs locally.

## How it works

The app is split into a **FastAPI backend service** and a **Streamlit UI client**,
with a **Qdrant** vector store and **Redis** FAQ cache running in Docker.
Ollama (LLM + embeddings) runs as a host process.

```
┌─ Streamlit UI (app.py) ───────────────────────────────┐
│  typed / wake-word / recorded audio                   │
└──────────────┬────────────────────────────────────────┘
               │  HTTP  (httpx / fetch)
┌──────────────▼────────────────────────────────────────┐
│  FastAPI service (server.py)                          │
│  /chat   /ingest   /voices   /health                  │
│                                                        │
│  Redis cache (exact + semantic)  →  hit?  return fast  │
│       │ miss                                            │
│       ▼                                                │
│  RAG (Qdrant, nomic-embed-text via Ollama)             │
│       ▼                                                │
│  LLM (Ollama · qwen3:4b-instruct-2507-q4_K_M)          │
│       ▼                                                │
│  TTS (Piper)  →  WAV bytes → base64 → back to client   │
└────────────────────────────────────────────────────────┘
```

- **faster-whisper** (small, CPU/int8) transcribes recorded audio inside `/chat`.
- Browser wake-word voice ("Hey Shakti") uses the Web Speech API and posts
  straight to `/chat`; the result is relayed to Streamlit for rendering.
- Redis serves repeat questions instantly (exact match + cosine-semantic).

## Hardware & why these models

| Component | Choice | Why |
|---|---|---|
| LLM | `qwen3:4b-instruct-2507-q4_K_M` | 4B, Q4 quantized (~2.5 GB). The **non-thinking** 2507 checkpoint — Qwen split thinking/non-thinking in 2507, and `-thinking-` variants prepend a reasoning preamble to every answer. Right size for 8 GB / integrated graphics. |
| Embeddings | `nomic-embed-text` | 768-dim, ~275 MB, runs fast on CPU via Ollama. |
| STT | `faster-whisper` `small` (int8) | Good accuracy/latency balance. Swap to `base` in `WHISPER_MODEL` if you want it faster. |
| TTS | Piper `en_US-lessac-medium` / `hi_IN-priyamvada-medium` | Fully offline, light (~63 MB voice). |
| Vector store | **Qdrant** (Docker, cosine, 768-dim) | Multi-worker-ready; ChromaDB still supported via `VECTOR_BACKEND=chroma` (used by tests). |
| Cache | **Redis 7** (Docker) | Exact + semantic FAQ cache with TTL. |

Two models are called every turn. We deliberately keep Ollama's **default**
single-resident-model setting to stay within 8 GB; each turn pays ~1–2 s of
model swap. To keep both hot (faster, more RAM), launch Ollama with
`OLLAMA_MAX_LOADED_MODELS=2`.

## Install (macOS)

Prerequisites: [Docker](https://www.docker.com/products/docker-desktop) (running),
[Ollama](https://ollama.com) (installed and running), Python 3.12.

```bash
# 1. Pull the models (~2.8 GB total)
ollama pull qwen3:4b-instruct-2507-q4_K_M
ollama pull nomic-embed-text

# 2. Project setup
cd shakti-bot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Piper needs a voice model, which is **not** bundled with the pip package.
It downloads automatically on first run; to grab it manually:

```bash
mkdir -p voices && cd voices
curl -L -o en_US-lessac-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -L -o en_US-lessac-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```

The first time you record, macOS will ask for **microphone permission**
(System Settings → Privacy & Security → Microphone) — grant it for your
terminal. faster-whisper also downloads its `small` weights (~460 MB) into
`~/.cache/huggingface` on first use.

## Run

Start the services, ingest your documents, then launch the API and the UI.

```bash
# 1. Start Qdrant + Redis (Docker)
docker compose up -d

# 2. Ingest PDFs from data/ into Qdrant
python -m src.ingest

# 3. Start the API (leave running)
uvicorn server:app --host 0.0.0.0 --port 8000

# 4. Start the UI (another terminal)
streamlit run app.py
```

Open the printed URL. Ask by **wake word** ("Hey Shakti"), **record manually**,
or **type** in the chat box. Enable **Show retrieved context** to debug which
chunks were used. Status shows each stage: Talking to Shakti Bot → … → Done.

Quick API sanity checks:

```bash
curl localhost:8000/health
curl -X POST localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"question":"What is the application fee?"}'        # first call: cached=false
# repeat the same call → cached:true (served from Redis, no LLM)
```

Configuration lives in `.env` (copy `.env.example`): `OLLAMA_HOST`,
`LLM_MODEL`, `EMBED_MODEL`, `VECTOR_BACKEND`, `QDRANT_URL`, `REDIS_URL`,
`API_BASE_URL`, `CACHE_THRESHOLD`, `CACHE_TTL`.

## Add your documents and ingest

1. Drop PDFs into `data/`.
2. Run the ingester:

```bash
python -m src.ingest
```

It extracts text (PyMuPDF), chunks paragraph-by-paragraph, embeds each chunk
with `nomic-embed-text`, and stores it in Qdrant. Re-running is safe —
already-indexed chunks are skipped via a content hash.

## Test

```bash
docker compose up -d        # Redis needed for the cache tests
python -m pytest tests -v
```

Covers Ollama connectivity, embedding generation, vector store read/write,
ingest + de-duplication, retrieval relevance, LLM answer generation, Piper
audio generation, the API endpoints (mocked pipeline), and the Redis cache
(exact + semantic hit, model gate, TTL). `test_cache.py` skips automatically
if Redis isn't reachable.

## Project layout

```
shakti-bot/
├── app.py            # Streamlit UI — httpx client of the API
├── server.py         # FastAPI service: /chat, /ingest, /voices, /health
├── docker-compose.yml  # qdrant + redis
├── src/
│   ├── config.py     # paths, models, knobs (env-overridable)
│   ├── ingest.py     # PDF → chunks → embeddings → vector store
│   ├── rag.py        # top-k retrieval for a question
│   ├── llm.py        # grounded answer generation (qwen3)
│   ├── vectorstore.py# Chroma-shaped Qdrant facade (backend switch)
│   ├── cache.py      # Redis exact + semantic FAQ cache
│   ├── stt.py        # faster-whisper transcription
│   ├── tts.py        # Piper speech synthesis (file + bytes)
│   └── utils.py      # shared helpers (embed, clean, hash)
├── data/             # drop PDFs here
├── chroma_db/        # legacy Chroma store (gitignored)
├── voices/           # downloaded Piper voices (gitignored)
└── tests/
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `could not connect to Ollama` | Start Ollama (menu-bar app or `ollama serve`), then check `curl localhost:11434/api/tags`. |
| `model not found` | `ollama pull qwen3:4b-instruct-2507-q4_K_M` and `ollama pull nomic-embed-text`. |
| Can't reach Qdrant/Redis | `docker compose up -d`, then `curl localhost:6333/collections` and `docker exec shakti-bot-redis-1 redis-cli ping`. |
| API down / UI shows "Couldn't reach Shakti API" | Start `uvicorn server:app` (step 3 above). |
| Mic fails / no audio captured | Grant mic permission in System Settings → Privacy & Security → Microphone; check the input device in System Settings → Sound. |
| Piper error / missing voice | Run the manual voice download above, or delete `voices/` and let the app re-download. |
| Qdrant store is wrong | Delete the `qdrant_storage/` volume (`docker compose down -v`) and re-run `python -m src.ingest`. |
| `ModuleNotFoundError` | `source .venv/bin/activate && pip install -r requirements.txt`. |
| Slow speech-to-text | Set `WHISPER_MODEL=base` in `.env` (from `.env.example`). |
