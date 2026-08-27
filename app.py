"""Shakti Bot — Streamlit client for the FastAPI service.

Run:  uvicorn server:app --port 8000   (backend)
Run:  streamlit run app.py            (this UI)
"""
import base64
import html
import json
import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from queue import Queue, Empty

import httpx
import streamlit as st

from src import config

# ======================================================================
# Result relay: the browser JS posts the API's chat result here so the
# Streamlit script can rerun and render it. (iframe JS cannot trigger a
# Streamlit rerun directly — this is the rendering handoff, not the pipeline.)
# ======================================================================
_result_queue: Queue = Queue()
_server_port: int | None = None
_server_lock = threading.Lock()


class _RelayHandler(BaseHTTPRequestHandler):
    """CORS-enabled handler that buffers chat results from the browser JS."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        try:
            data = json.loads(body)
            if data.get("answer"):
                _result_queue.put(data)
        except Exception:
            pass
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, *_args):
        pass


def _ensure_relay_server() -> int:
    """Start the result-relay HTTP server once per process, return port."""
    global _server_port
    with _server_lock:
        if _server_port is not None:
            return _server_port
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        srv = HTTPServer(("127.0.0.1", port), _RelayHandler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _server_port = port
        return port


relay_port = _ensure_relay_server()

# ======================================================================
# Streamlit page setup
# ======================================================================
st.set_page_config(page_title="Shakti Bot", page_icon="🎓", layout="centered")

CUSTOM_CSS = """
<style>
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
</style>
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


def _autoplay(audio_bytes):
    """Play the generated audio automatically (autoplay policy permitting)."""
    b64 = base64.b64encode(audio_bytes).decode()
    st.components.v1.html(
        f'<audio autoplay src="data:audio/wav;base64,{b64}"></audio>', height=0
    )


# Voice choices (bare .onnx names — matched against the API's /voices)
VOICE_OPTIONS = {
    "🇮🇳 Priyamvada (Indian Female)": "hi_IN-priyamvada-medium.onnx",
    "🇺🇸 Amy (US Female)": "en_US-amy-medium.onnx",
    "🇺🇸 Lessac (US Female)": "en_US-lessac-medium.onnx",
    "🇺🇸 Ryan (US Male)": "en_US-ryan-medium.onnx",
}


def _ask(question=None, audio_bytes=None, voice_name=None):
    """Call the Shakti API. Returns {answer, audio_wav_base64, cached, chunks?}."""
    with st.status("Talking to Shakti Bot…", expanded=False):
        if audio_bytes is not None:
            r = httpx.post(
                f"{config.API_BASE_URL}/chat",
                files={"audio_wav": audio_bytes},
                data={"voice": voice_name or "", "debug": "true"},
                timeout=120,
            )
        else:
            r = httpx.post(
                f"{config.API_BASE_URL}/chat",
                json={"question": question, "voice": voice_name or "", "debug": True},
                timeout=120,
            )
        r.raise_for_status()
        return r.json()


def store_results(body):
    st.session_state["results"] = body
    st.session_state["needs_autoplay"] = True
    st.rerun()


# ---- sidebar ----
with st.sidebar:
    st.markdown(f'<div class="qa-label">{_icon("sparkle")} Assistant Voice</div>', unsafe_allow_html=True)
    voice_label = st.selectbox(
        "Voice",
        list(VOICE_OPTIONS.keys()),
        index=0,
        label_visibility="collapsed",
    )
    st.session_state["selected_voice"] = VOICE_OPTIONS[voice_label]

    st.divider()
    st.markdown(f'<div class="qa-label">{_icon("note")} Try asking</div>', unsafe_allow_html=True)
    for q in ["What is the application fee for MIT ADT?",
              "Where is the university located?",
              "Which schools are at MIT ADT?",
              "When did MIT ADT launch?"]:
        if st.button(q, use_container_width=True):
            st.session_state["quick"] = q
    st.divider()
    st.caption(f"Backend API: {config.API_BASE_URL}. Voice uses faster-whisper + Piper, served by the API.")


# ======================================================================
# Wake-word listener (browser Web Speech API → API /chat → relay → rerun)
# ======================================================================

WAKE_WORD_HTML = """
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
         background: transparent; color: #e2e8f0; overflow: hidden; }
  .wk { display: flex; align-items: center; justify-content: center; gap: 12px;
        padding: 12px 20px; border-radius: 14px; cursor: pointer; user-select: none;
        background: linear-gradient(135deg, rgba(139,92,246,0.12), rgba(34,211,238,0.08));
        border: 1px solid rgba(139,92,246,0.3); transition: all 0.3s ease; }
  .wk:hover { border-color: rgba(139,92,246,0.6); background: linear-gradient(135deg, rgba(139,92,246,0.2), rgba(34,211,238,0.14)); }
  .wk.on { background: linear-gradient(135deg, rgba(139,92,246,0.18), rgba(34,211,238,0.12));
            border-color: rgba(139,92,246,0.5); box-shadow: 0 0 20px rgba(139,92,246,0.15); }
  .wk.hot { background: linear-gradient(135deg, rgba(34,211,238,0.22), rgba(139,92,246,0.16));
             border-color: rgba(34,211,238,0.7); box-shadow: 0 0 25px rgba(34,211,238,0.25); }

  .dot { width: 14px; height: 14px; border-radius: 50%; background: #64748b;
         flex-shrink: 0; transition: background 0.3s; }
  .on .dot { background: #8b5cf6; animation: p 2s ease-in-out infinite; }
  .hot .dot { background: #22d3ee; animation: p2 .8s ease-in-out infinite; }
  @keyframes p  { 0%,100%{box-shadow:0 0 0 0 rgba(139,92,246,.4)} 50%{box-shadow:0 0 0 8px rgba(139,92,246,0)} }
  @keyframes p2 { 0%,100%{box-shadow:0 0 0 0 rgba(34,211,238,.5)} 50%{box-shadow:0 0 0 10px rgba(34,211,238,0)} }

  .lbl { font-size: .92rem; color: #94a3b8; transition: color .3s; line-height: 1.3; }
  .on .lbl { color: #c4b5fd; font-weight: 500; }
  .hot .lbl { color: #67e8f9; font-weight: 600; }
  .sub { font-size: .8rem; color: rgba(148,163,184,.6); font-style: italic; margin-top: 2px; }
</style>

<div class="wk on" id="c" title="Click to ask directly or say 'Hey Shakti'">
  <div class="dot"></div>
  <div>
    <div class="lbl" id="l">Say "Hey Shakti" or click here to ask…</div>
    <div class="sub" id="s"></div>
  </div>
</div>

<script>
const API_BASE = "__API_BASE__";
const RELAY_PORT = __RELAY_PORT__;
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const c = document.getElementById("c");
const l = document.getElementById("l");
const s = document.getElementById("s");

function matchWakeWord(rawText) {
  if (!rawText) return null;
  const clean = rawText.toLowerCase().replace(/[,.?!;:\\-_/]/g, " ").replace(/\\s+/g, " ").trim();
  const wakeRegex = /\\b(?:hey|hi|hello|ok|okay|a)?\\s*(?:shakti|sakti|shakthi|shukti|shocked|shackt|shakt|shak)\\b(?:\\s*bot)?/i;
  const match = wakeRegex.exec(clean);
  if (!match) return null;
  const after = clean.substring(match.index + match[0].length).trim();
  return { matchedPhrase: match[0], after: after, clean: clean };
}

if (!SR) {
  l.textContent = "Voice recognition not supported in this browser (use Chrome or Edge)";
} else {
  let rec = null;
  let mode = "idle"; // "idle" | "question" | "sending"
  let timer = null;
  let questionText = "";

  function startRecognizer() {
    if (rec) {
      try { rec.abort(); } catch(e){}
    }
    rec = new SR();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-IN";

    rec.onresult = handleResult;
    rec.onerror = handleError;
    rec.onend = handleEnd;

    try {
      rec.start();
      setIdleState();
    } catch(e) {
      l.textContent = "Mic access issue: " + e.message;
    }
  }

  function setIdleState() {
    mode = "idle";
    questionText = "";
    clearTimeout(timer);
    c.className = "wk on";
    l.textContent = 'Say "Hey Shakti" or click here to ask…';
    s.textContent = "";
  }

  function setQuestionState(initialText) {
    mode = "question";
    questionText = initialText || "";
    c.className = "wk hot";
    l.textContent = questionText ? ("Hearing: " + questionText + "…") : "Listening… ask your question now";
    s.textContent = "";
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (questionText.length > 3) {
        submitQuestion(questionText);
      } else {
        setIdleState();
      }
    }, 7000);
  }

  function submitQuestion(q) {
    q = q.trim();
    if (q.length < 2) { setIdleState(); return; }

    mode = "sending";
    clearTimeout(timer);
    c.className = "wk hot";
    l.textContent = "✓ Got it: " + q;
    s.textContent = "Sending to Shakti Bot…";

    try { rec.abort(); } catch(e){}

    fetch(API_BASE + "/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question: q, debug: true})
    })
    .then(r => r.json())
    .then(data => {
      l.textContent = "⏳ Thinking & Speaking: " + q;
      s.textContent = "";
      // Forward the result to the local relay so Streamlit can render it.
      return fetch("http://127.0.0.1:" + RELAY_PORT, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          question: q, answer: data.answer,
          audio_wav_base64: data.audio_wav_base64,
          cached: data.cached, chunks: data.chunks || null
        })
      });
    })
    .catch(e => {
      l.textContent = "Error: " + e.message;
    })
    .finally(() => {
      setTimeout(startRecognizer, 4000);
    });
  }

  function handleResult(ev) {
    if (mode === "sending") return;

    let finalTranscript = "";
    let interimTranscript = "";

    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const item = ev.results[i];
      if (item.isFinal) {
        finalTranscript += item[0].transcript + " ";
      } else {
        interimTranscript += item[0].transcript;
      }
    }

    const currentSpoken = (finalTranscript + " " + interimTranscript).trim();

    if (mode === "idle") {
      s.textContent = interimTranscript ? ("…" + interimTranscript) : "";

      const wake = matchWakeWord(currentSpoken);
      if (wake) {
        if (wake.after && wake.after.length > 2) {
          setQuestionState(wake.after);
          if (finalTranscript.trim().length > 0) {
            clearTimeout(timer);
            timer = setTimeout(() => submitQuestion(wake.after), 1200);
          }
        } else {
          setQuestionState("");
        }
      }
    } else if (mode === "question") {
      let cleanSpoken = currentSpoken.toLowerCase().replace(/[,.?!;:\\-_/]/g, " ").trim();
      const wake = matchWakeWord(cleanSpoken);
      const textToUse = wake ? wake.after : cleanSpoken;

      if (textToUse) {
        questionText = textToUse;
        l.textContent = "Hearing: " + questionText + "…";
      }

      if (finalTranscript.trim().length > 0 && interimTranscript.trim().length === 0) {
        clearTimeout(timer);
        timer = setTimeout(() => {
          if (questionText.length > 2) {
            submitQuestion(questionText);
          }
        }, 1200);
      }
    }
  }

  function handleError(ev) {
    if (ev.error === "no-speech" || ev.error === "aborted") return;
    if (ev.error === "not-allowed") {
      l.textContent = "Mic permission denied (enable in browser address bar)";
    } else {
      console.warn("Speech error:", ev.error);
    }
  }

  function handleEnd() {
    if (mode !== "sending") {
      setTimeout(() => {
        try { rec.start(); } catch(e){}
      }, 300);
    }
  }

  c.addEventListener("click", () => {
    setQuestionState("");
  });

  startRecognizer();
}
</script>
""".replace("__RELAY_PORT__", str(relay_port)).replace("__API_BASE__", config.API_BASE_URL)

# ---- Result poller: checks queue every second, triggers app rerun ----
@st.fragment(run_every="1s")
def _result_poller():
    try:
        body = _result_queue.get_nowait()
        store_results(body)
    except Empty:
        pass

_result_poller()

# Render the wake word listener
st.components.v1.html(WAKE_WORD_HTML, height=65)

# ---- or record manually (audio goes to the API for transcription) ----
with st.expander("Or record manually", expanded=False):
    audio_bytes = st.audio_input("Record a question")
    if audio_bytes is not None:
        try:
            body = _ask(audio_bytes=audio_bytes.getvalue(), voice_name=st.session_state.get("selected_voice"))
            body["question"] = "(voice recording)"
            store_results(body)
        except Exception as e:
            st.error(f"Couldn't reach Shakti API: {e}")

# ---- or type / quick-pick a question ----
typed = st.chat_input("…or type your question here")
quick = st.session_state.pop("quick", None)
if quick or typed:
    question = (quick or typed).strip()
    if question:
        try:
            body = _ask(question=question, voice_name=st.session_state.get("selected_voice"))
            body["question"] = question
            store_results(body)
        except Exception as e:
            st.error(f"Couldn't reach Shakti API: {e}")

# ---- results ----
r = st.session_state.get("results")
if r:
    audio_bytes = base64.b64decode(r["audio_wav_base64"])
    st.divider()
    st.markdown(f'<div class="qa-label">{_icon("note")} Your question</div>', unsafe_allow_html=True)
    st.markdown(f"**{html.escape(r['question'])}**")
    st.markdown(f'<div class="qa-label" style="margin-top:1rem;">{_icon("forum")} Answer</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="answer-card">{html.escape(r["answer"])}</div>', unsafe_allow_html=True)
    st.audio(audio_bytes, format="audio/wav")
    if r.get("cached"):
        st.caption("⚡ Answered from cache.")
    if st.session_state.pop("needs_autoplay", False):
        _autoplay(audio_bytes)
    st.session_state["show_debug"] = st.toggle(
        "Show retrieved context", value=st.session_state.get("show_debug", False))
    if st.session_state["show_debug"] and r.get("chunks"):
        with st.expander("Retrieved chunks", expanded=True):
            for i, c in enumerate(r["chunks"], 1):
                st.markdown(f"**{i}.** `{c['metadata']['filename']}` · page {c['metadata']['page']} · distance {c['distance']:.3f}")
                st.caption(c["text"])
else:
    st.caption("No question yet — say **\"Hey Shakti\"** and ask, or type below.")
