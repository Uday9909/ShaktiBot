"""Vector store abstraction: Chroma (PersistentClient) or Qdrant (HTTP).

`get_collection()` returns an object with the Chroma surface used by
`rag.retrieve` and `ingest.ingest_document`:
  query(query_texts, n_results) -> {"documents": [[...]], "metadatas": [[...]], "distances": [[...]]}
  add(ids, documents, metadatas)
  get(ids, include=[]) -> {"ids": [...]}
  count() -> int

Qdrant is the production backend; Chroma remains available when a local
`path` is passed (tests) or VECTOR_BACKEND=chroma.
"""
import uuid

import chromadb
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    VectorParams,
)

from . import config, utils

# nomic-embed-text output dimension
EMBED_DIM = 768
# Qdrant point ids must be UUIDs — map the sha256 content hash onto one.
_NS = uuid.NAMESPACE_DNS


def _point_id(sha: str) -> str:
    return str(uuid.uuid5(_NS, sha))


class OllamaEmbeddingFunction(chromadb.EmbeddingFunction):
    """Embed documents via Ollama so ChromaDB never loads its own model."""

    def __init__(self):
        pass

    def name(self) -> str:
        return "ollama-nomic"

    def __call__(self, input):
        return [utils.embed_text(d) for d in input]


class _QdrantCollection:
    """Minimal Chroma-shaped facade over a Qdrant collection."""

    def __init__(self, client, name):
        self._client = client
        self._name = name
        if not client.collection_exists(name):
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
            )

    def add(self, ids, documents, metadatas):
        self._client.upsert(
            collection_name=self._name,
            points=[
                {
                    "id": _point_id(i),
                    "vector": utils.embed_text(d),
                    "payload": {"_id": i, **m, "text": d},
                }
                for i, d, m in zip(ids, documents, metadatas)
            ],
        )

    def query(self, query_texts, n_results, category=None):
        vector = utils.embed_text(query_texts[0])
        query_filter = None
        if category:
            query_filter = Filter(must=[FieldCondition(key="category", match=MatchValue(value=category))])
        res = self._client.query_points(
            collection_name=self._name,
            query=vector,
            limit=n_results,
            with_payload=True,
            query_filter=query_filter,
        )
        docs, metas, dists = [], [], []
        for p in res.points:
            docs.append(p.payload.get("text", ""))
            metas.append({k: v for k, v in p.payload.items() if k not in ("text", "_id")})
            # Qdrant returns cosine similarity; Chroma reports distance (1 - sim).
            dists.append(round(1.0 - p.score, 6))
        return {"documents": [docs], "metadatas": [metas], "distances": [dists]}

    def get(self, ids, include=[]):
        found = self._client.retrieve(
            collection_name=self._name,
            ids=[_point_id(i) for i in ids],
            with_payload=True,
        )
        return {"ids": [p.payload["_id"] for p in found]}

    def get_document_ids(self, filename):
        points, _ = self._client.scroll(
            collection_name=self._name,
            scroll_filter=Filter(must=[FieldCondition(key="filename", match=MatchValue(value=filename))]),
            with_payload=True,
            limit=10000,
        )
        return [p.payload["_id"] for p in points]

    def delete(self, ids):
        self._client.delete(
            collection_name=self._name,
            points_selector=PointIdsList(points=[_point_id(i) for i in ids]),
        )

    def count(self):
        return self._client.count(collection_name=self._name).count


def get_collection(path=None, name=None):
    """Return a Chroma collection (path given or VECTOR_BACKEND=chroma) or Qdrant facade."""
    if path is not None or config.VECTOR_BACKEND == "chroma":
        client = chromadb.PersistentClient(path=str(path or config.CHROMA_DIR))
        collection = client.get_or_create_collection(
            name or config.COLLECTION,
            embedding_function=OllamaEmbeddingFunction(),
            metadata={"hnsw:space": "cosine"},
        )
        return collection
    return _QdrantCollection(QdrantClient(url=config.QDRANT_URL), name or config.COLLECTION)
