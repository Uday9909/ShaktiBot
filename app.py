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
<style>
:root { --accent:#6d28d9; --ink:#1e1b4b; }
.stApp { background: linear-gradient(180deg, #fafaff 0%, #f3f1ff 100%); }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.2rem; max-width: 760px; }
h1 { font-family: -apple-system, "Segoe UI", sans-serif; letter-spacing: -0.02em; }
.hero { text-align: center; padding: 1rem 1rem 0.4rem; }
.hero .title { font-size: 2.7rem; font-weight: 800; color: var(--ink); line-height: 1.1; }
.hero .title span { background: linear-gradient(90deg,#6d28d9,#9333ea,#db2777);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
.hero .sub { color: #6b7280; margin-top: 0.4rem; font-size: 1.05rem; }
.answer-card { background: #ffffff; border: 1px solid #e5e7eb; border-left: 5px solid var(--accent);
  border-radius: 14px; padding: 1.1rem 1.3rem; box-shadow: 0 4px 14px rgba(109,40,217,.08);
  font-size: 1.08rem; line-height: 1.6; color: var(--ink); }
.qa-label { color: #6b7280; font-size: .82rem; text-transform: uppercase; letter-spacing: .06em;
  margin-bottom: .2rem; }
div.stButton > button, [data-testid="stChatInput"] { border-radius: 12px; }
div.stButton > button:hover { border-color: var(--accent); color: var(--accent); }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown(
    '<div class="hero"><div class="title">🎓 Shakti <span>Bot</span></div>'
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
        status.update(label="🔎 Searching college knowledge…")
        chunks = rag.retrieve(question)
        status.update(label="🧠 Thinking…")
        answer = llm.generate(question, chunks)
        status.update(label="🗣️ Speaking…")
        audio_path = os.path.join(tempfile.gettempdir(), f"shakti_{abs(hash(question))}.wav")
        tts.synthesize(answer, audio_path)
        status.update(label="✅ Done", state="complete")
    _autoplay(audio_path)
    return answer, chunks, audio_path


def store_results(question, answer, chunks, audio):
    st.session_state["results"] = {"question": question, "answer": answer,
                                   "chunks": chunks, "audio": audio}
    st.rerun()


# ---- quick-ask sidebar ----
with st.sidebar:
    st.markdown("### ✨ Try asking")
    for q in ["What is the application fee for MIT ADT?",
              "Where is the university located?",
              "Which schools are at MIT ADT?",
              "When did MIT ADT launch?"]:
        if st.button(q, use_container_width=True):
            st.session_state["quick"] = q
    st.divider()
    st.caption("Voice uses faster-whisper + Piper. Everything runs locally on your Mac.")

# ---- voice: click once, speak, it auto-stops on pause ----
if st.button("🎤 Ask by voice", use_container_width=True):
    frames = []
    with st.status("Listening…", expanded=False) as status:
        status.update(label="🎤 Listening… speak now — it stops when you pause")
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
    st.markdown('<div class="qa-label">Your question</div>', unsafe_allow_html=True)
    st.markdown(f"**{html.escape(r['question'])}**")
    st.markdown('<div class="qa-label" style="margin-top:1rem;">Answer</div>', unsafe_allow_html=True)
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
