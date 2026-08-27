"""Shakti Bot — local voice RAG assistant (Streamlit UI).

Run:  streamlit run app.py
"""
import base64
import html
import os
import tempfile

import streamlit as st

from src import llm, rag, stt, tts

st.set_page_config(page_title="Shakti Bot", page_icon="🎓", layout="centered")

CUSTOM_CSS = """
:root { --accent:#8b5cf6; --text:#e2e8f0; --muted:#94a3b8; --card:#181d2e; }
.stApp { background: linear-gradient(180deg, #0b0d14 0%, #131829 100%); }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.2rem; max-width: 760px; }
h1 { letter-spacing: -0.02em; }
.hero { text-align: center; padding: 1rem 1rem 0.4rem; }
.hero .title { font-size: 2.6rem; font-weight: 800; color: var(--text); line-height: 1.2; }
.hero .title .grad { background: linear-gradient(90deg,#8b5cf6,#22d3ee);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
.hero .sub { color: var(--muted); margin-top: 0.4rem; font-size: 1.05rem; }
.answer-card { background: var(--card); border: 1px solid #2a3247; border-left: 5px solid var(--accent);
  border-radius: 14px; padding: 1.1rem 1.3rem; box-shadow: 0 6px 20px rgba(0,0,0,.35);
  font-size: 1.08rem; line-height: 1.6; color: var(--text); }
.qa-label { color: var(--muted); font-size: .82rem; text-transform: uppercase; letter-spacing: .06em;
  margin-bottom: .2rem; }
div.stButton > button { border-radius: 12px; }
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Inline SVG icons (Material Design paths) — no font/CDN dependency, works offline.
_ICONS = {
    "cap": "M5 13.18v4L12 21l7-3.82v-4L12 17l-7-3.82zM12 3L1 9l11 6 9-4.91V17h2V9L12 3z",
    "sparkle": "M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z",
    "note": "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z",
    "forum": "M21 6h-2v9H6v2c0 .55.45 1 1 1h11l4 4V7c0-.55-.45-1-1-1zm-4 6V3c0-.55-.45-1-1-1H3c-.55 0-1 .45-1 1v14l4-4h10c.55 0 1-.45 1-1z",
}


def _icon(name, size="1.15em"):
    """Render an icon as a base64 SVG <img> — survives Streamlit's markdown sanitizer."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
           f'fill="#8b5cf6"><path d="{_ICONS[name]}"/></svg>')
    b64 = base64.b64encode(svg.encode()).decode()
    return (f'<img src="data:image/svg+xml;base64,{b64}" alt="" '
            f'style="width:{size};height:{size};vertical-align:-0.18em;display:inline-block;">')


st.markdown(
    f'<div class="hero"><div class="title">{_icon("cap")} Shakti <span class="grad">Bot</span></div>'
    '<div class="sub">Your college&apos;s local AI assistant — grounded answers from your own documents.</div></div>',
    unsafe_allow_html=True,
)


def _autoplay(audio_path):
    """Play the generated audio automatically (autoplay policy permitting)."""
    b64 = base64.b64encode(open(audio_path, "rb").read()).decode()
    st.components.v1.html(
        f'<audio autoplay src="data:audio/wav;base64,{b64}"></audio>', height=0
    )


def run_pipeline(question):
    """Full text -> RAG -> LLM -> TTS. Returns (answer, chunks, audio_path)."""
    with st.status("Searching college knowledge…", expanded=False) as status:
        status.update(label="Searching college knowledge…")
        chunks = rag.retrieve(question)
        status.update(label="Thinking…")
        answer = llm.generate(question, chunks)
        status.update(label="Speaking…")
        audio_path = os.path.join(tempfile.gettempdir(), f"shakti_{abs(hash(question))}.wav")
        tts.synthesize(answer, audio_path)
        status.update(label="Done", state="complete")
    _autoplay(audio_path)
    return answer, chunks, audio_path


def store_results(question, answer, chunks, audio):
    st.session_state["results"] = {"question": question, "answer": answer,
                                   "chunks": chunks, "audio": audio}
    st.rerun()


# ---- quick-ask sidebar ----
with st.sidebar:
    st.markdown(f'<div class="qa-label">{_icon("sparkle")} Try asking</div>', unsafe_allow_html=True)
    for q in ["What is the application fee for MIT ADT?",
              "Where is the university located?",
              "Which schools are at MIT ADT?",
              "When did MIT ADT launch?"]:
        if st.button(q, use_container_width=True):
            st.session_state["quick"] = q
    st.divider()
    st.caption("Voice uses faster-whisper + Piper. Everything runs locally on your Mac.")

# ---- voice: click once, speak, it auto-stops on pause ----
if st.button("Ask by voice", use_container_width=True):
    frames = []
    with st.status("Listening…", expanded=False) as status:
        status.update(label="Listening… speak now — it stops when you pause")
        wav = stt.record_until_silence(frames)
    if wav is None:
        st.info("No speech detected — try again.")
    else:
        try:
            question = stt.transcribe(wav)
        finally:
            os.unlink(wav)
        if question:
            answer, chunks, audio = run_pipeline(question)
            store_results(question, answer, chunks, audio)
        else:
            st.warning("Couldn't hear anything — speak up or check the mic.")

# ---- or type / quick-pick a question ----
typed = st.chat_input("…or type your question here")
quick = st.session_state.pop("quick", None)
if quick or typed:
    question = (quick or typed).strip()
    if question:
        answer, chunks, audio = run_pipeline(question)
        store_results(question, answer, chunks, audio)

# ---- results ----
r = st.session_state.get("results")
if r:
    st.divider()
    st.markdown(f'<div class="qa-label">{_icon("note")} Your question</div>', unsafe_allow_html=True)
    st.markdown(f"**{html.escape(r['question'])}**")
    st.markdown(f'<div class="qa-label" style="margin-top:1rem;">{_icon("forum")} Answer</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="answer-card">{html.escape(r["answer"])}</div>', unsafe_allow_html=True)
    if os.path.exists(r["audio"]):
        st.audio(r["audio"], format="audio/wav")
    st.session_state["show_debug"] = st.toggle(
        "Show retrieved context", value=st.session_state.get("show_debug", False))
    if st.session_state["show_debug"]:
        with st.expander("Retrieved chunks", expanded=True):
            for i, c in enumerate(r["chunks"], 1):
                st.markdown(f"**{i}.** `{c['metadata']['filename']}` · page {c['metadata']['page']} · distance {c['distance']:.3f}")
                st.caption(c["text"])
else:
    st.caption("No question yet — press **Ask by voice** and speak, or type below.")
