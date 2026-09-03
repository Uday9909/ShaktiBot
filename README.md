# 🎓 Shakti Bot — Local Voice RAG Assistant

A college AI assistant that answers questions about clubs, policies, events, and
more — **entirely offline**. Speak a question (or type it), get a spoken answer
grounded in your own PDF documents.

Built for a **MacBook Air M2 / 8 GB RAM**. No cloud APIs, no large LLMs, no heavy
frameworks. Everything runs locally.

## How it works

The app is split into a **FastAPI backend service** and a **Streamlit UI client**,
with a **Qdrant** vector store and **Redis** FAQ cache — all five services
(Ollama, Qdrant, Redis, API, UI) run in Docker via `docker compose`.

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

## Quick start (Docker)

Prerequisite: [Docker](https://www.docker.com/products/docker-desktop)
(running) — nothing else.

```bash
# 1. Start the whole stack (first run pulls ~2.8 GB of models — be patient)
docker compose up -d --build

# 2. Drop your PDFs into data/, then index them
curl -X POST localhost:8000/ingest
#   (or: docker compose exec api python -m src.ingest)

# 3. Open the UI
#    http://localhost:8501
```

Open the printed URL. Ask by **wake word** ("Hey Shakti"), **record manually**,
or **type** in the chat box. Enable **Show retrieved context** to debug which
chunks were used.

- First boot downloads the Ollama LLM + embedding models (~2.8 GB) and the
  Whisper weights (~460 MB); later boots are instant (persisted in named
  volumes). Piper voices auto-download into `voices/` on the first answer.
- `data/` and `voices/` are bind-mounted, so you edit them on the host
  directly. Re-running the ingester is safe — already-indexed chunks are
  skipped via a content hash.

Quick API sanity checks:

```bash
curl localhost:8000/health
curl -X POST localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"question":"What is the application fee?"}'        # first call: cached=false
# repeat the same call → cached:true (served from Redis, no LLM)
```

### Configuration

All knobs are env vars (copy `.env.example` to `.env`): `LLM_MODEL`,
`EMBED_MODEL`, `WHISPER_MODEL`, `TOP_K`, `CHUNK_WORDS`, `CACHE_THRESHOLD`,
`CACHE_TTL`. The browser-facing URL `BROWSER_API_BASE_URL` defaults to
`http://localhost:8000` — set it to your machine's LAN IP if you open the UI
from another device.

### Hardware notes

Ollama now runs inside Docker — give Docker Desktop **at least 6 GB of
memory**. `qwen3:4b` needs ~2.5 GB plus `nomic-embed-text` ~300 MB resident
(we keep both hot via `OLLAMA_MAX_LOADED_MODELS=2`). The whole stack sits
around 4–5 GB.

### Run without Docker (for development)

```bash
docker compose up -d qdrant redis          # infra only
ollama pull qwen3:4b-instruct-2507-q4_K_M && ollama pull nomic-embed-text
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.ingest
uvicorn server:app --host 0.0.0.0 --port 8000   # API
streamlit run app.py                            # UI (another terminal)
```

The first time you record, macOS will ask for **microphone permission**
(System Settings → Privacy & Security → Microphone) — grant it for your
terminal. faster-whisper downloads its `small` weights (~460 MB) into
`~/.cache/huggingface` on first use.

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
docker compose up -d --build       # full stack (Redis + Qdrant + Ollama needed)
docker compose exec api python -m pytest tests -v
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
├── docker-compose.yml  # full stack: ollama, qdrant, redis, api, web
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
| `could not connect to Ollama` | `docker compose logs ollama`; the API container must resolve `ollama:11434` (only true inside the compose network). |
| `model not found` | Models pull automatically on boot; force a re-pull with `docker compose exec ollama ollama pull qwen3:4b-instruct-2507-q4_K_M`. |
| Can't reach Qdrant/Redis | `docker compose up -d`, then `curl localhost:6333/collections` and `docker compose exec redis redis-cli ping`. |
| API down / UI shows "Couldn't reach Shakti API" | `docker compose logs api`; if you run the UI outside Docker, point `BROWSER_API_BASE_URL`/`API_BASE_URL` at `http://localhost:8000`. |
| Whisper/Piper model re-download on every boot | The named volumes (`model_cache`, `voices/`) persist them — don't run `docker compose down -v` unless you want a clean slate. |
| Mic fails / no audio captured | Grant mic permission in System Settings → Privacy & Security → Microphone; check the input device in System Settings → Sound. |
| Piper error / missing voice | Run the manual voice download above, or delete `voices/` and let the app re-download. |
| Qdrant store is wrong | Delete the `qdrant_storage/` volume (`docker compose down -v`) and re-run `python -m src.ingest`. |
| `ModuleNotFoundError` | `source .venv/bin/activate && pip install -r requirements.txt`. |
| Slow speech-to-text | Set `WHISPER_MODEL=base` in `.env` (from `.env.example`). |

---

## Cinematic Avatar (`/cinematic/`)

A fullscreen, video-state AI avatar frontend. It shows one of five short
pre-recorded avatar videos depending on what Shakti is doing — listening,
searching, thinking, or speaking — and drives everything over the FastAPI
WebSocket, exactly like the chat API but visual.

The UI is plain HTML/CSS/JS — **no build step, no Node, no frameworks**. The
same `server.py` FastAPI app serves it statically (add-only mounts; no backend
logic changed). The original Streamlit UI (`app.py`) still runs separately on
`:8501`.

### Run

```bash
uvicorn server:app --reload --port 8000
```

Then open **http://localhost:8000/cinematic/**

Type a question (or tap the mic and speak — Web Speech API, language-aware:
`en-IN` / `hi-IN` / `mr-IN`), choose a response **language** and **persona**
(Visitor / Parent / Student), and watch Shakti crossfade through her states.
The status chip top-centre shows the current state; the dot is the live
WebSocket connection (green = connected, amber = reconnecting, red = down).

**How it talks to the backend**

- Primary: WebSocket to `/ws/chat`, sending one JSON `ChatRequest`
  (`{question, persona, lang, debug}`). Server frames drive the state machine
  (`listening → searching → thinking → speaking → idle`) and stream sentence
  audio; the client plays the audio in order and only returns to `idle` once
  the final clip has finished.
- Fallback: if the WebSocket can't connect, the page POSTs the same
  `ChatRequest` to `/chat` (HTTP) and plays the returned full answer.
- Override the socket host with a URL param, e.g.
  `http://localhost:8000/cinematic/?ws=ws://127.0.0.1:8000`.

### Where the videos live

The five avatar MP4s are expected in **`videos/`** at the repo root (served at
`/videos/…`). They are original AI-generated files — do not rename or move
them; filenames with spaces/parentheses are URL-encoded automatically.

| State | File (in `videos/`) |
|---|---|
| `idle` | `Reference_image_upload_the_S.mp4` |
| `listening` | `Reference_image_upload_the_S (1).mp4` |
| `searching` | `for_the_video_generated_above.mp4` |
| `thinking` | `Her_eyes_dart_left_and_right_a (1).mp4` |
| `speaking` | `She_speaks_with_a_warm_confid.mp4` |

### Change the mapping

The state → video map is one clearly-labelled object at the top of
**`cinematic/app.js`** (the `VIDEOS` constant). Edit the filenames there to
point at different clips — nothing else needs to change. New videos go in
`videos/`.
