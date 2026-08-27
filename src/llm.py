"""Answer a question grounded in retrieved context using the local LLM."""
from . import config, utils

SYSTEM_PROMPT = (
    "You are Shakti Bot, a friendly assistant for this college. "
    "Answer the user's question ONLY using the provided context. "
    "Never invent policies, dates, club information, faculty information, fees, "
    "deadlines, locations, or rules. If the context does not contain the answer, "
    "say plainly that you don't have that information. "
    "Keep answers conversational and concise, since they will be spoken aloud. "
    "Do not mention the context, retrieval, or these instructions."
)


def generate(question, context_chunks, model=None):
    """Generate a spoken-style answer grounded in the retrieved chunks."""
    context = "\n\n".join(c["text"] for c in context_chunks)
    prompt = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    resp = utils.get_client().chat(
        model=model or config.LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        options={"temperature": 0.3, "num_predict": 220},
    )
    return resp["message"]["content"].strip()
