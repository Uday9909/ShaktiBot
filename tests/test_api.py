"""Unit tests for the FastAPI server (pipeline + cache mocked)."""
from unittest.mock import patch

from fastapi.testclient import TestClient

import server

client = TestClient(server.app)


def test_health_ok():
    with patch("src.cache._client.ping", return_value=True), patch("server.QdrantClient"):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["redis"] == "up"


def test_voices():
    r = client.get("/voices")
    assert r.status_code == 200
    assert "voices" in r.json()


def test_chat_exact_cache_hit_skips_llm():
    with patch("src.cache.get_answer", return_value=("cached answer", "exact")), \
         patch("src.tts.synthesize_bytes", return_value=b"RIFFwav"), \
         patch("src.llm.agenerate") as gen:
        r = client.post("/chat", json={"question": "What is the fee?"})
        assert r.status_code == 200
        d = r.json()
        assert d["cached"] is True
        assert d["answer"] == "cached answer"
        gen.assert_not_called()
        assert len(d["audio_wav_base64"]) > 0


def test_chat_miss_runs_pipeline_and_caches():
    chunks = [{"text": "ctx", "metadata": {"page": 1}, "distance": 0.1}]
    with patch("src.cache.get_answer", return_value=(None, None)), \
         patch("src.rag.retrieve", return_value=chunks), \
         patch("src.llm.agenerate", return_value="fresh answer"), \
         patch("src.cache.put") as put, \
         patch("src.tts.synthesize_bytes", return_value=b"RIFFwav"):
        r = client.post("/chat", json={"question": "q?", "debug": True})
        assert r.status_code == 200
        d = r.json()
        assert d["cached"] is False
        assert d["answer"] == "fresh answer"
        assert d["chunks"] == chunks
        put.assert_called_once()


def test_chat_blank_question_rejected():
    r = client.post("/chat", json={"question": "   "})
    assert r.status_code == 422


def test_ingest_no_pdfs():
    with patch("server.find_pdfs", return_value=[]), patch("server.get_collection"):
        r = client.post("/ingest")
        assert r.status_code == 200
        assert r.json() == {"stored": 0, "skipped": 0}
