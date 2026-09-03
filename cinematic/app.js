/* Shakti Cinematic Avatar — vanilla JS state machine driving the
   fullscreen 5-video crossfade against the FastAPI /ws/chat stream.

   Primary path: WebSocket. Fallback: POST /chat (HTTP) when WS is unavailable.
   No external libraries, no build step. */
'use strict';

/* =====================================================================
   EDIT ME: state -> avatar video file (relative to the /videos mount).
   Filenames with spaces/parens are URL-encoded automatically via encodeURI.
   ===================================================================== */
const VIDEOS = {
  idle:      'Reference_image_upload_the_S.mp4',
  listening: 'Reference_image_upload_the_S (1).mp4',
  searching: 'for_the_video_generated_above.mp4',
  thinking:  'Her_eyes_dart_left_and_right_a (1).mp4',
  speaking:  'She_speaks_with_a_warm_confid.mp4',
};

const STATE_LABEL = {
  idle: 'Ask Shakti anything',
  listening: 'Listening…',
  searching: 'Searching…',
  thinking: 'Thinking…',
  speaking: 'Speaking…',
};

/* Optional overrides. WS_BASE is a ws://host:port base (empty = same origin).
   A ?ws= URL param wins over WS_BASE. */
const WS_BASE = '';
const RECONNECT_MIN_MS = 1000;
const RECONNECT_MAX_MS = 8000;
const OPEN_FALLBACK_MS = 2500; /* wait for a fresh socket, then fall back to HTTP */

/* ---------------------------------------------------------------- DOM */
const $ = (id) => document.getElementById(id);
const els = {
  status: $('status'),
  dot: $('dot'),
  answerPanel: $('answerPanel'),
  answerText: $('answerText'),
  answerClose: $('answerClose'),
  userBubble: $('userBubble'),
  userBubbleText: $('userBubbleText'),
  form: $('bar'),
  q: $('q'),
  askBtn: $('askBtn'),
  mic: $('btnMic'),
  lang: $('lang'),
  persona: $('persona'),
  toast: $('toast'),
};

/* --------------------------------------------------------- Video layer */
const videos = {};
document.querySelectorAll('#stage video').forEach((v) => {
  const state = v.getAttribute('data-state');
  videos[state] = v;
  v.src = '/videos/' + encodeURI(VIDEOS[state]);
});
/* The idle video may autoplay muted from page load (allowed w/o a gesture). */

let currentState = null;
let warmed = false;

function setState(s) {
  if (!videos[s]) return;
  if (s === currentState) return;
  currentState = s;
  Object.keys(videos).forEach((k) => {
    const video = videos[k];
    if (k === s) {
      video.classList.add('active');
      const p = video.play();
      if (p) p.catch(() => {});
    } else {
      video.classList.remove('active');
      video.pause();
    }
  });
  els.status.textContent = STATE_LABEL[s] || s;
}

function warmVideos() {
  if (warmed) return;
  warmed = true;
  Object.values(videos).forEach((v) => {
    v.muted = true;
    const p = v.play();
    if (p) p.catch(() => {});
  });
  /* Pause non-active clips once they have painted a frame (keeps CPU low). */
  setTimeout(() => {
    Object.keys(videos).forEach((k) => {
      if (k !== currentState) videos[k].pause();
    });
  }, 700);
}
window.addEventListener('pointerdown', warmVideos);
window.addEventListener('keydown', warmVideos);

/* ------------------------------------------------------------ Audio out */
const audioEl = new Audio();
audioEl.preload = 'auto';
audioEl.style.display = 'none';
document.body.appendChild(audioEl);

let audioQueue = [];
let audioPlaying = false;

function b64ToBlob(b64, mime) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime || 'audio/wav' });
}

function enqueueAudio(frames) {
  for (const f of frames) {
    if (!f.audio_base64) continue;
    let blob;
    try {
      blob = b64ToBlob(f.audio_base64, f.audio_format || 'audio/wav');
    } catch (err) {
      console.warn('[cinematic] bad audio frame dropped', err);
      continue;
    }
    audioQueue.push(URL.createObjectURL(blob));
  }
  playNext();
}

function playNext() {
  if (audioPlaying) return;
  const url = audioQueue.shift();
  if (!url) return;
  audioPlaying = true;
  audioEl.src = url;
  const p = audioEl.play();
  if (p) p.catch(() => audioDone());
}

function audioDone() {
  audioPlaying = false;
  if (audioEl.src) {
    URL.revokeObjectURL(audioEl.src);
    audioEl.removeAttribute('src');
    audioEl.load();
  }
  if (audioQueue.length) playNext();
  else if (currentState === 'speaking') setState('idle');
}
audioEl.addEventListener('ended', audioDone);
audioEl.addEventListener('error', audioDone);

function cancelAudio() {
  audioPlaying = false;
  audioQueue = [];
  if (audioEl.src) {
    URL.revokeObjectURL(audioEl.src);
    audioEl.removeAttribute('src');
    audioEl.load();
  }
}

/* ------------------------------------------------------------ Utilities */
let toastTimer = null;
function toast(message) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { els.toast.hidden = true; }, 3800);
}

function showAnswer(text) {
  els.answerText.textContent = text || '';
  els.answerText.scrollTop = 0;
  els.answerPanel.hidden = !(text && text.trim());
}
function showUserBubble(text) {
  if (!text || !text.trim()) { els.userBubble.hidden = true; return; }
  els.userBubbleText.textContent = text;
  els.userBubble.hidden = false;
}

function setDot(kind) {
  els.dot.classList.remove('ok', 'busy', 'down');
  if (kind) els.dot.classList.add(kind);
}

/* Server 'idle' arrives before the client finishes playing audio, so only
   honour it once nothing is playing/queued. The queue drain drives idle. */
function applyServerState(name, text) {
  if (name === 'idle') {
    if (!audioPlaying && audioQueue.length === 0 && currentState !== 'idle') {
      setState('idle');
    }
  } else if (name === 'speaking') {
    if (text) showAnswer(text);
    setState('speaking');
  } else {
    setState(name);
  }
}

function failAnswer(message) {
  if (message) toast(message);
  pendingSend = null;
  awaitingServer = false;
  cancelAudio();
  if (currentState !== 'idle') setState('idle');
}

/* ---------------------------------------------------- WebSocket layer */
let sock = null;
let connecting = false;
let reconnectAttempt = 0;
let reconnectTimer = null;
let sendWatch = null;
let pendingSend = null;      /* {payload, token} waiting for a socket to open */
let sockToken = 0;           /* request token carried by the current socket */
let awaitingServer = false;  /* question in flight, complete frame not seen */
let currentToken = 0;        /* latest request token (stale frames are dropped) */

function wsUrl() {
  const param = new URLSearchParams(location.search).get('ws') || WS_BASE;
  if (param) return param.replace(/\/+$/, '') + '/ws/chat';
  const proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
  return proto + location.host + '/ws/chat';
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  if (document.hidden) return;
  reconnectAttempt += 1;
  const delay = Math.min(RECONNECT_MIN_MS * 2 ** (reconnectAttempt - 1), RECONNECT_MAX_MS);
  reconnectTimer = setTimeout(() => {
    if (!sock && !connecting && !document.hidden) connect();
  }, delay);
}

function connect() {
  if (sock || connecting) return;
  connecting = true;
  setDot('busy');
  let s;
  try {
    s = new WebSocket(wsUrl());
  } catch (err) {
    console.warn('[cinematic] ws construct failed', err);
    connecting = false;
    scheduleReconnect();
    return;
  }
  s.addEventListener('open', () => onWsOpen(s));
  s.addEventListener('message', (ev) => onWsMessage(s, ev));
  s.addEventListener('error', () => { /* close follows */ });
  s.addEventListener('close', () => onWsClose(s));
  sock = s;
}

function onWsOpen(s) {
  connecting = false;
  reconnectAttempt = 0;
  setDot('ok');
  sockToken = 0;
  if (pendingSend && pendingSend.token === currentToken) {
    const queued = pendingSend;
    pendingSend = null;
    sendOnSocket(s, queued.payload, queued.token);
  }
}

function onWsMessage(s, ev) {
  if (s !== sock || sockToken !== currentToken) return; /* stale socket/exchange */
  let msg;
  try {
    msg = JSON.parse(ev.data);
  } catch (err) {
    console.warn('[cinematic] non-JSON frame dropped');
    return;
  }
  if (!msg || typeof msg !== 'object') return;
  switch (msg.type) {
    case 'state':
      applyServerState(msg.state, msg.text);
      break;
    case 'audio':
      enqueueAudio([msg]);
      break;
    case 'complete':
      awaitingServer = false;
      break;
    case 'error':
      failAnswer(msg.detail || 'Something went wrong.');
      break;
    default:
      console.log('[cinematic] unknown frame', msg.type);
  }
}

function onWsClose(s) {
  if (s !== sock) return; /* superseded by a newer socket */
  sock = null;
  connecting = false;
  if (awaitingServer) {
    /* Dropped mid-answer (no complete frame). */
    awaitingServer = false;
    failAnswer('Connection lost — please ask again.');
  } else {
    setDot('down');
  }
  if (!document.hidden) scheduleReconnect();
}

function sendOnSocket(s, payload, token) {
  try {
    s.send(JSON.stringify(payload));
  } catch (err) {
    console.warn('[cinematic] ws send failed', err);
    sock = null;
    connecting = false;
    httpFallback(payload, token);
    return;
  }
  sockToken = token;
  awaitingServer = true;
  setState('listening');
}

function armSendWatch(payload, token) {
  clearTimeout(sendWatch);
  sendWatch = setTimeout(() => {
    if (token !== currentToken) return;
    const open = sock && sock.readyState === WebSocket.OPEN;
    if (pendingSend && pendingSend.token === token && !open) {
      pendingSend = null;
      httpFallback(payload, token);
    }
  }, OPEN_FALLBACK_MS);
}

function sendQuestion(rawText) {
  const text = (rawText || '').trim();
  if (!text) return;
  currentToken += 1;
  const token = currentToken;
  awaitingServer = false;      /* fresh interaction supersedes anything in flight */
  clearTimeout(sendWatch);
  cancelAudio();
  showUserBubble(text);

  const payload = {
    question: text,
    persona: els.persona.value,
    lang: els.lang.value,
    debug: false,
  };

  /* Reuse the open idle socket if it exists and is unused. */
  if (sock && sock.readyState === WebSocket.OPEN && sockToken === 0) {
    sendOnSocket(sock, payload, token);
    return;
  }
  /* Otherwise open a fresh socket just for this question. */
  const old = sock;
  sock = null;
  connecting = false;
  if (old && old.readyState !== WebSocket.CLOSED) {
    try { old.close(); } catch (err) { /* ignore */ }
  }
  pendingSend = { payload, token };
  armSendWatch(payload, token);
  connect();
}

/* ----------------------------------------------- HTTP fallback (POST /chat) */
async function httpFallback(payload, token) {
  if (token !== currentToken) return;
  awaitingServer = true;
  setState('searching');
  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (token !== currentToken) return;
    if (!res.ok) {
      let detail = 'Request failed (' + res.status + ').';
      try { detail = (await res.json()).detail || detail; } catch (err) { /* ignore */ }
      throw new Error(detail);
    }
    const data = await res.json();
    if (token !== currentToken) return;
    awaitingServer = false;
    setState('thinking');
    setTimeout(() => {
      if (token !== currentToken) return;
      setState('speaking');
      showAnswer(data.answer);
      enqueueAudio([{ audio_base64: data.audio_wav_base64, audio_format: data.audio_format || 'audio/wav' }]);
    }, 850);
  } catch (err) {
    if (token !== currentToken) return;
    awaitingServer = false;
    failAnswer('Could not reach Shakti: ' + (err && err.message ? err.message : err));
  }
}

/* ---------------------------------------------------------------- Mic */
const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec = null;
let recActive = false;

function startMic() {
  if (!SpeechRec) {
    toast('Voice input is not supported in this browser — please type.');
    return;
  }
  recActive = true;
  els.mic.classList.add('on');
  setState('listening');
  rec = new SpeechRec();
  const map = { en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN' };
  rec.lang = map[els.lang.value] || 'en-IN';
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  rec.onresult = (e) => {
    const transcript = (e.results[0][0].transcript || '').trim();
    stopMic();
    if (transcript) sendQuestion(transcript);
  };
  rec.onerror = (e) => {
    const label = e.error === 'not-allowed' ? 'Microphone access denied.'
      : e.error === 'no-speech' ? 'No speech heard.'
      : e.error === 'audio-capture' ? 'No microphone found.'
      : 'Voice input error.';
    stopMic();
    toast(label + ' Please type your question instead.');
  };
  rec.onend = () => {
    const wasActive = recActive;
    stopMic();
    if (wasActive && currentState === 'listening') setState('idle');
  };
  try {
    rec.start();
  } catch (err) {
    stopMic();
    toast('Could not start the microphone.');
  }
}

function stopMic() {
  recActive = false;
  els.mic.classList.remove('on');
  if (rec) {
    try { rec.abort(); } catch (err) { /* ignore */ }
    rec = null;
  }
}

els.mic.addEventListener('click', () => {
  if (recActive) { stopMic(); if (currentState === 'listening') setState('idle'); }
  else startMic();
});

/* ----------------------------------------------------------- Inputs */
els.form.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = els.q.value;
  els.q.value = '';
  sendQuestion(text);
});

els.answerClose.addEventListener('click', () => {
  els.answerPanel.hidden = true;
  els.userBubble.hidden = true;
});

/* ------------------------------------------------------- Lifecycle */
function cleanup() {
  clearTimeout(reconnectTimer);
  clearTimeout(sendWatch);
  awaitingServer = false;
  pendingSend = null;
  if (sock) { try { sock.close(); } catch (err) { /* ignore */ } }
  sock = null;
  cancelAudio();
}
window.addEventListener('pagehide', cleanup);
window.addEventListener('visibilitychange', () => {
  if (!document.hidden && !sock && !connecting) scheduleReconnect();
});

console.log('[cinematic] ready — connect + idle');
connect();
setState('idle');
