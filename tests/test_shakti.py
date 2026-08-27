"""Tests for Shakti Bot. Run: python -m pytest tests -v

All model calls hit the local Ollama / Piper runtime — no external APIs.
"""
import wave

import pytest

from src import config, llm, rag, tts, utils
from src.ingest import get_collection, ingest_document


def test_ollama_connectivity():
    assert "models" in utils.get_client().list()


def test_embedding_generation():
    emb = utils.embed_text("hello world")
    assert len(emb) > 0
    assert all(isinstance(x, float) for x in emb[:5])


def test_chromadb_read_write(tmp_path):
    col = get_collection(path=str(tmp_path / "chroma"), name="test")
    col.add(ids=["a"], documents=["Tech club meets Thursdays"], metadatas=[{"filename": "t.txt", "page": 1}])
    assert col.get(ids=["a"], include=["documents"])["documents"] == ["Tech club meets Thursdays"]


@pytest.fixture
def sample_pdf(tmp_path):
    import pymupdf

    path = tmp_path / "sample.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(
        pymupdf.Rect(72, 72, 540, 720),
        "The dance club meets every Friday at 6pm in the Student Center, room S-210.\n\n"
        "The chess club meets on Wednesdays at noon in the library lobby.",
    )
    doc.save(str(path))
    return path


def test_ingest_end_to_end(tmp_path, sample_pdf):
    col = get_collection(path=str(tmp_path / "chroma"), name="test")
    pages, stored, skipped = ingest_document(sample_pdf, col)
    assert pages >= 1
    assert stored >= 1
    assert col.count() == stored


def test_ingest_deduplicates(tmp_path, sample_pdf):
    col = get_collection(path=str(tmp_path / "chroma"), name="test")
    ingest_document(sample_pdf, col)
    _, stored, skipped = ingest_document(sample_pdf, col)
    assert stored == 0
    assert skipped >= 1


def test_retrieval_relevance(tmp_path, sample_pdf):
    col = get_collection(path=str(tmp_path / "chroma"), name="test")
    ingest_document(sample_pdf, col)
    hits = rag.retrieve("When does the dance club meet?", collection=col, k=2)
    assert any("Friday" in h["text"] for h in hits)


def test_llm_answer_generation():
    chunks = [{"text": "The chess club meets Wednesdays at noon in the library lobby."}]
    answer = llm.generate("Where does the chess club meet?", chunks)
    assert len(answer) > 0


def test_piper_audio_generation(tmp_path):
    out = str(tmp_path / "voice.wav")
    tts.synthesize("Hello there.", out)
    with wave.open(out) as w:
        assert w.getnframes() > 0
