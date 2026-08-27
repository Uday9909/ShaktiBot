# 🎓 Shakti Bot — Local Voice RAG Assistant

A college AI assistant that answers questions about clubs, policies, events, and
more — **entirely offline**. Speak a question (or type it), get a spoken answer
grounded in your own PDF documents.

Built for a **MacBook Air M2 / 8 GB RAM**. No cloud APIs, no large LLMs, no heavy
frameworks. Everything runs locally.

## How it works

```
MICROPHONE (push-to-talk)
   ↓
SPEECH TO TEXT   faster-whisper (small, CPU/int8)
   ↓
RAG RETRIEVAL    ChromaDB + nomic-embed-text (via Ollama)
   ↓
LOCAL LLM        Ollama · qwen3:4b-instruct-2507-q4_K_M
   ↓
TEXT RESPONSE
   ↓
TEXT TO SPEECH   Piper (en_US-lessac-medium)
   ↓
AUDIO OUTPUT
```

## Hardware & why these models

| Component | Choice | Why |
|---|---|---|
| LLM | `qwen3:4b-instruct-2507-q4_K_M` | 4B, Q4 quantized (~2.5 GB). The **non-thinking** 2507 checkpoint — Qwen split thinking/non-thinking in 2507, and `-thinking-` variants prepend a reasoning preamble to every answer. Right size for 8 GB / integrated graphics. |
| Embeddings | `nomic-embed-text` | 768-dim, ~275 MB, runs fast on CPU via Ollama. |
| STT | `faster-whisper` `small` (int8) | Good accuracy/latency balance. Swap to `base` in `WHISPER_MODEL` if you want it faster. |
| TTS | Piper `en_US-lessac-medium` | Fully offline, light (~63 MB voice). |
| Vector store | ChromaDB (persistent) | Local file-backed, no server. |

Two models are called every turn. We deliberately keep Ollama's **default**
single-resident-model setting to stay within 8 GB; each turn pays ~1–2 s of
model swap. To keep both hot (faster, more RAM), launch Ollama with
`OLLAMA_MAX_LOADED_MODELS=2`.

## Install (macOS)

Prerequisites: [Ollama](https://ollama.com) installed and running, Python 3.12.

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

The first time you press **Push to talk**, macOS will ask for **microphone
permission** (System Settings → Privacy & Security → Microphone) — grant it for
your terminal. faster-whisper also downloads its `small` weights (~460 MB) into
`~/.cache/huggingface` on first use.

## Add your documents and ingest

1. Drop PDFs into `data/`.
2. Run the ingester:

```bash
python -m src.ingest
```

It extracts text (PyMuPDF), chunks paragraph-by-paragraph, embeds each chunk
with `nomic-embed-text`, and stores it in `chroma_db/`. Re-running is safe —
already-indexed chunks are skipped via a content hash.

## Run the app

```bash
streamlit run app.py
```

Open the printed URL. Ask by **Push to talk** (speak, then **Stop**) or by
typing in the chat box. Enable **Show retrieved context** to debug which chunks
were used. Status shows each stage: Listening → Transcribing → Searching →
Thinking → Speaking.

## Test

```bash
python -m pytest tests -v
```

Covers Ollama connectivity, embedding generation, ChromaDB read/write, one
document ingested end-to-end, de-duplication, retrieval relevance, LLM answer
generation, and Piper audio generation. No external APIs.

## Project layout

```
shakti-bot/
├── app.py            # Streamlit UI + pipeline orchestration
├── src/
│   ├── config.py     # paths, models, knobs (env-overridable)
│   ├── ingest.py     # PDF → chunks → embeddings → ChromaDB
│   ├── rag.py        # top-k retrieval for a question
│   ├── llm.py        # grounded answer generation (qwen3)
│   ├── stt.py        # sounddevice recording + faster-whisper
│   ├── tts.py        # Piper speech synthesis
│   └── utils.py      # shared helpers (embed, clean, hash)
├── data/             # drop PDFs here
├── chroma_db/        # generated vector store (gitignored)
├── voices/           # downloaded Piper voice (gitignored)
└── tests/
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `could not connect to Ollama` | Start Ollama (menu-bar app or `ollama serve`), then check `curl localhost:11434/api/tags`. |
| `model not found` | `ollama pull qwen3:4b-instruct-2507-q4_K_M` and `ollama pull nomic-embed-text`. |
| Mic fails / no audio captured | Grant mic permission in System Settings → Privacy & Security → Microphone; check the input device in System Settings → Sound. |
| Piper error / missing voice | Run the manual voice download above, or delete `voices/` and let the app re-download. |
| ChromaDB errors | Delete `chroma_db/` and re-run `python -m src.ingest`. |
| `ModuleNotFoundError` | `source .venv/bin/activate && pip install -r requirements.txt`. |
| Slow speech-to-text | Set `WHISPER_MODEL=base` in `.env` (from `.env.example`). |
