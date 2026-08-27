"""Redis semantic cache tests — require a reachable Redis, else skip."""
import time

import pytest

from src import cache

MODEL = "nomic-embed-text"


def _redis_available() -> bool:
    try:
        return bool(cache._client.ping())
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_available(), reason="Redis not reachable")


@pytest.fixture(autouse=True)
def _clean_cache():
    cache._client.flushdb()
    yield


def test_exact_hit_normalizes_case_spacing():
    cache.put("What is the application fee?", "The fee is Rs 1000.", MODEL)
    answer, source = cache.get_answer("  WHAT   IS the application fee? ", MODEL)
    assert (answer, source) == ("The fee is Rs 1000.", "exact")


def test_semantic_paraphrase_hit():
    cache.put("What does MIT ADT cost to apply?", "Apply costs Rs 1000.", MODEL)
    answer, source = cache.get_answer("How much does it cost to apply?", MODEL)
    assert source == "semantic"
    assert answer == "Apply costs Rs 1000."


def test_model_mismatch_is_miss():
    cache.put("What is the application fee?", "The fee is Rs 1000.", MODEL)
    answer, source = cache.get_answer("What is the application fee?", "some-other-model")
    assert (answer, source) == (None, None)


def test_unrelated_question_is_miss():
    cache.put("What is the application fee?", "The fee is Rs 1000.", MODEL)
    answer, source = cache.get_answer("What are the library timings?", MODEL)
    assert (answer, source) == (None, None)


def test_ttl_expiry(monkeypatch):
    monkeypatch.setattr(cache.config, "CACHE_TTL", 1)
    cache.put("How many schools exist?", "Five schools.", MODEL)
    assert cache.get_answer("How many schools exist?", MODEL)[0] == "Five schools."
    time.sleep(1.1)
    assert cache.get_answer("How many schools exist?", MODEL)[0] is None
