# data/

Drop college documents (PDFs) here, then run:

    python -m src.ingest

Each PDF is extracted, chunked, embedded with `nomic-embed-text`, and stored
in `../chroma_db`. Re-running the ingest only adds new chunks — existing ones
are skipped via a content hash, so it's safe to re-run after adding PDFs.

See the top-level README for the full setup and run instructions.
