"""Retrieve relevant chunks from the vector store for a question."""
from . import config
from .vectorstore import get_collection


def retrieve(question, collection=None, k=None, category=None):
    """Return top-k chunks as [{"text", "metadata", "distance"}]."""
    collection = collection or get_collection()
    k = k or config.TOP_K
    if category:
        try:
            res = collection.query(query_texts=[question], n_results=k, category=category)
        except TypeError:
            res = collection.query(query_texts=[question], n_results=k, where={"category": category})
    else:
        res = collection.query(query_texts=[question], n_results=k)
    out = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        out.append({"text": doc, "metadata": meta, "distance": dist})
    return [chunk for chunk in out if chunk["distance"] <= config.RAG_DISTANCE_THRESHOLD]
