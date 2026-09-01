# ShaktiBot Improvements

## Product direction

ShaktiBot is intentionally optimized as a fast, polished first-contact campus
guide and marketing/demo assistant. It is not intended to be a full agent that
submits forms, manages calendars, or performs general-purpose tasks.

## Completed improvements

- Centralized configuration loading and removed duplicate environment settings.
- Added validated JSON chat requests with question length and category validation.
- Added a 10 MB limit for uploaded audio.
- Added document categories inferred from filenames: `admission`, `student_life`, `hostel`, and `general`.
- Added category-aware retrieval for both Qdrant and Chroma backends.
- Added a configurable retrieval distance threshold so weak matches are not sent to the LLM.
- Added source filename and page metadata to the LLM context for citations.
- Removed stale chunks when an indexed PDF changes.
- Clears the Redis answer cache after ingestion so answers reflect the current documents.
- Makes short overview answers the default by reducing LLM output to 120 tokens.
- Keeps TTS offline by default with Piper; Edge TTS is opt-in via `TTS_PROVIDER=edge`.
- Separates cached answers by category so filtered questions cannot reuse another category.
- Preserves the API audio MIME type through the browser wake-word relay.
- Reduces LLM temperature to 0.2 for more consistent short answers.
- Adds `LLM_NUM_PREDICT` configuration, defaulting to 120 tokens for faster
	overview responses and shorter speech output.
- Adds `TTS_PROVIDER` configuration. Piper is now the default offline provider;
	Edge TTS is opt-in with `TTS_PROVIDER=edge`.
- Keeps cache entries separate by category, preventing an admission answer from
	being reused for a hostel or student-life query.
- Adds visitor, parent, and student personas to the API and Streamlit UI.
- Adds English, Hindi, and Marathi response-language selection.
- Adds timezone-aware current-date context to answer prompts.
- Adds `/ws/chat` state events and sentence-level audio for future animated clients.
- Adds configurable localhost CORS, per-client request limiting, and `503` readiness responses.
- Adds chunk overlap to preserve meaning across document boundaries.
- Adds request IDs, duration/status logging, and exception logging for API,
  cache, TTS, and microphone failures.
- Adds compatible dependency version ranges and a GitHub Actions test workflow.
- Makes the default voice English so the default English responses are clearly understandable.
- Adds language-matched Hindi and Marathi neural speech in automatic TTS mode;
	English remains on offline Piper by default.

## Verification

- `python -m compileall -q server.py src` passes.
- API tests pass: `6 passed`.
- Editor diagnostics report no errors in the changed Python files.
- Redis integration tests are currently skipped when Redis is unavailable.

The model-backed integration tests require Ollama with the configured embedding
model installed, plus the local Qdrant service and indexed PDFs.

## Next improvements

1. Add tests for categories, stale chunks, thresholds, personas, languages, and WebSockets.
2. Add a polished welcome screen with campus highlights and curated demo questions.
3. Add a protected admin upload/ingestion portal only if staff need to manage documents.