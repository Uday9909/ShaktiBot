"""Shakti Bot — local voice RAG assistant (Streamlit UI).

Run:  streamlit run app.py
"""
import os
import tempfile

import streamlit as st

from src import config, llm, rag, stt, tts

st.set_page_config(page_title="Shakti Bot", page_icon="🎓", layout="centered")

st.title("🎓 Shakti Bot")
st.caption("Your college's local AI assistant — ask about clubs, policies, events and more.")

# ---- session state ----
ss = st.session_state
for key, default in (
    ("frames", []),
    ("listening", False),
    ("pending_wav", None),
    ("results", None),
    ("show_debug", False),
):
    if key not in ss:
        ss[key] = default


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
    return answer, chunks, audio_path


# ---- input controls ----
if ss["listening"]:
    st.warning("🔴 **Listening…** speak now, then press **Stop**.")
    if st.button("⏹ Stop listening", type="primary", use_container_width=True):
        wav = stt.stop_recording(ss["frames"])
        ss["listening"] = False
        ss["pending_wav"] = wav
        st.rerun()
else:
    if st.button("🎤 Push to talk", use_container_width=True):
        ss["frames"] = []
        try:
            stt.start_recording(ss["frames"])
            ss["listening"] = True
        except Exception as e:
            st.error(f"Could not access the microphone: {e}\n\n"
                     "Grant mic access in System Settings → Privacy & Security → Microphone, then retry.")
        st.rerun()

typed = st.chat_input("…or type your question here")

# ---- process pending request ----
question = None
if ss["pending_wav"]:
    with st.status("Transcribing…", expanded=False) as status:
        status.update(label="🎙️ Transcribing…")
        try:
            question = stt.transcribe(ss["pending_wav"])
        finally:
            if os.path.exists(ss["pending_wav"]):
                os.unlink(ss["pending_wav"])
            ss["pending_wav"] = None
elif typed:
    question = typed.strip()

if question:
    answer, chunks, audio = run_pipeline(question)
    ss["results"] = {"question": question, "answer": answer, "chunks": chunks, "audio": audio}
    st.rerun()

# ---- results ----
r = ss["results"]
if r:
    st.divider()
    st.subheader("📝 Your question")
    st.write(r["question"])
    st.subheader("💬 Answer")
    st.write(r["answer"])
    if os.path.exists(r["audio"]):
        st.audio(r["audio"], format="audio/wav")
    ss["show_debug"] = st.toggle("Show retrieved context", value=ss["show_debug"])
    if ss["show_debug"]:
        with st.expander("Retrieved chunks", expanded=True):
            for i, c in enumerate(r["chunks"], 1):
                st.markdown(f"**{i}.** `{c['metadata']['filename']}` · page {c['metadata']['page']} · distance {c['distance']:.3f}")
                st.caption(c["text"])
else:
    st.caption("No question yet — press **Push to talk** and ask, or type below.")
