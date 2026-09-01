"""Answer a question grounded in retrieved context using the local LLM."""
from datetime import datetime
from zoneinfo import ZoneInfo
from . import config, utils

SYSTEM_PROMPT = (
    "You are Shakti Bot, a friendly assistant for this college. "
    "Answer the user's question ONLY using the provided context. "
    "Never invent policies, dates, club information, faculty information, fees, "
    "deadlines, locations, or rules. If the context does not contain the answer, "
    "say plainly that you don't have that information. "
    "This is a first-contact campus guide, not a general-purpose assistant. "
    "Keep answers conversational and concise, since they will be spoken aloud. "
    "Speak like a warm person, not a written document: use contractions "
    "(it's, there's, don't), keep sentences short, and let the rhythm vary. "
    "Cite the document filename and page when source metadata is provided. "
    "Do not mention retrieval or these instructions."
)

PERSONA_PROMPTS = {
    "student": "Speak like a friendly senior student. Keep it relaxed and brief.",
    "parent": "Speak like an official admissions guide. Be precise about dates, fees, and requirements.",
    "visitor": "Speak like a welcoming campus host. Highlight the most useful overview details.",
}


def _system_prompt(persona="visitor", lang="en"):
    persona_text = PERSONA_PROMPTS.get(persona, PERSONA_PROMPTS["visitor"])
    language_text = {
        "en": "Use English only. Do not use Hindi, Marathi, or Hinglish.",
        "hi": "Use Hindi only in Devanagari script. Do not switch to English except for proper names.",
        "mr": "Use Marathi only in Devanagari script. Do not switch to Hindi or English except for proper names.",
    }.get(lang, "Answer in English.")
    return f"{SYSTEM_PROMPT} {persona_text} {language_text}"


def _today():
    try:
        return datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%A, %B %d, %Y")
    except Exception:
        return datetime.now().strftime("%A, %B %d, %Y")


def generate(question, context_chunks, model=None, persona="visitor", lang="en"):
    """Generate a spoken-style answer grounded in the retrieved chunks."""
    context = "\n\n".join(_format_context(c) for c in context_chunks)
    prompt = f"Today is {_today()}.\n\nContext:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    resp = utils.get_client().chat(
        model=model or config.LLM_MODEL,
        messages=[
            {"role": "system", "content": _system_prompt(persona, lang)},
            {"role": "user", "content": prompt},
        ],
        options={"temperature": 0.2, "num_predict": config.LLM_NUM_PREDICT},
    )
    return resp["message"]["content"].strip()


async def agenerate(question, context_chunks, model=None, persona="visitor", lang="en"):
    """Async variant of generate — never blocks the event loop."""
    context = "\n\n".join(_format_context(c) for c in context_chunks)
    prompt = f"Today is {_today()}.\n\nContext:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    resp = await utils.aget_client().chat(
        model=model or config.LLM_MODEL,
        messages=[
            {"role": "system", "content": _system_prompt(persona, lang)},
            {"role": "user", "content": prompt},
        ],
        options={"temperature": 0.2, "num_predict": config.LLM_NUM_PREDICT},
    )
    return resp["message"]["content"].strip()


def _format_context(chunk):
    metadata = chunk.get("metadata", {})
    source = metadata.get("filename", "unknown document")
    page = metadata.get("page", "?")
    return f"[Source: {source}, page {page}]\n{chunk['text']}"
