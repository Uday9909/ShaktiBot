"""Redis semantic FAQ cache.

Two layers:
  1. Exact match: key `q:{model}:{normalized question}` -> answer (fast path, O(1)).
  2. Semantic: every stored Q&A also gets an `entry:{sha}` hash holding
     {question, embedding, answer, model}; a miss embeds the incoming
     question once and brute-force cosine-scans those entries.

Both layers are gated on the embedder model so a model swap never serves
stale embeddings. All operations fail soft (try/except -> miss) so the
cache can never break the pipeline.
"""
import hashlib
import json
import logging

import redis

from . import config, utils

_client = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
logger = logging.getLogger(__name__)

# ponytail: brute-force cosine over entry:* — fine to ~1k cached questions,
# swap to RediSearch HNSW (FT.CREATE ... AS distance cosine) past that.


def _norm(question: str) -> str:
    return " ".join(question.lower().split())


def _key_prefix(model: str, category: str | None, persona: str, lang: str) -> str:
    return f"v2:{model}:{category or 'all'}:{persona}:{lang}"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def get_answer(question: str, model: str, category: str | None = None,
               persona: str = "visitor", lang: str = "en"):
    """Return (answer, source) on a hit, else (None, None). Never raises."""
    try:
        prefix = _key_prefix(model, category, persona, lang)
        exact = _client.get(f"q:{prefix}:{_norm(question)}")
        if exact is not None:
            return exact, "exact"
        emb = utils.embed_text(question)
        best = None
        for key in _client.scan_iter("entry:v2:*"):
            e = _client.hgetall(key)
            if (e.get("model") != model
                    or e.get("category", "all") != (category or "all")
                    or e.get("persona", "visitor") != persona
                    or e.get("lang", "en") != lang):
                continue
            sim = _cosine(emb, json.loads(e["embedding"]))
            if sim >= config.CACHE_THRESHOLD and (best is None or sim > best[1]):
                best = (e["answer"], sim)
        if best:
            return best[0], "semantic"
    except Exception:
        logger.exception("cache_lookup_failed")
    return None, None


def put(question: str, answer: str, model: str, category: str | None = None,
    persona: str = "visitor", lang: str = "en") -> None:
    """Store an answer in both cache layers. Never raises."""
    try:
        prefix = _key_prefix(model, category, persona, lang)
        _client.setex(f"q:{prefix}:{_norm(question)}", config.CACHE_TTL, answer)
        key = f"entry:v2:{hashlib.sha256(question.encode()).hexdigest()}"
        _client.hset(
            key,
            mapping={
                "question": question,
                "embedding": json.dumps(utils.embed_text(question)),
                "answer": answer,
                "model": model,
                "category": category or "all",
                "persona": persona,
                "lang": lang,
            },
        )
        _client.expire(key, config.CACHE_TTL)
    except Exception:
        logger.exception("cache_write_failed")


def clear() -> None:
    """Clear cached answers after the source document index changes."""
    try:
        keys = list(_client.scan_iter("q:*")) + list(_client.scan_iter("entry:*"))
        if keys:
            _client.delete(*keys)
    except Exception:
        logger.exception("cache_clear_failed")
