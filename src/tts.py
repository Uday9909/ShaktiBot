import io
import os
import re
import urllib.request
import wave
from pathlib import Path

import numpy as np

from . import config

# Voice catalog for auto-download if missing
VOICE_URLS = {
    "hi_IN-priyamvada-medium": "https://huggingface.co/rhasspy/piper-voices/resolve/main/hi/hi_IN/priyamvada/medium/hi_IN-priyamvada-medium.onnx",
    "en_US-lessac-medium": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
    "en_US-amy-medium": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx",
    "en_US-ryan-medium": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/medium/en_US-ryan-medium.onnx",
}

# Written → spoken fixes that keep Piper from sounding robotic.
ABBREVIATIONS = {
    "e.g.": "for example",
    "i.e.": "that is",
    "etc.": "and so on",
    "Dr.": "Doctor",
    "Prof.": "Professor",
    "vs.": "versus",
    "&": "and",
}

_voices_cache = {}


def naturalize_text(text: str) -> str:
    """Rewrite answer text so it reads naturally when spoken."""
    t = re.sub(r"Rs\.?\s*([\d,]+)", r"\1 rupees", text)
    for k, v in ABBREVIATIONS.items():
        t = t.replace(k, v)
    return re.sub(r"\s+", " ", t).strip()


def _pace_config():
    """Piper synthesis settings for human-sounding pacing (not fast/flat defaults)."""
    from piper.config import SynthesisConfig

    return SynthesisConfig(length_scale=1.08, noise_scale=0.72, noise_w_scale=0.9)


def ensure_voice_downloaded(voice_path: str = None) -> Path:
    """Download the Piper voice ONNX model + config if missing."""
    voice = Path(voice_path or config.PIPER_VOICE)
    if voice.exists():
        return voice
    stem = voice.stem
    url = VOICE_URLS.get(stem)
    if not url:
        # Fallback to Priyamvada (Indian Female)
        url = VOICE_URLS["hi_IN-priyamvada-medium"]
        voice = config.VOICES_DIR / "hi_IN-priyamvada-medium.onnx"
        if voice.exists():
            return voice

    print(f"Voice model not found at {voice}. Downloading {stem} ...")
    voice.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, voice)
    urllib.request.urlretrieve(url + ".json", str(voice) + ".json")
    return voice


def _load_voice(voice_path: str = None):
    target = str(ensure_voice_downloaded(voice_path))
    if target not in _voices_cache:
        from piper import PiperVoice
        _voices_cache[target] = PiperVoice.load(target)
    return _voices_cache[target]


def synthesize(text, out_path, voice_path: str = None):
    """Generate speech for `text` into `out_path`. Returns the path."""
    voice = _load_voice(voice_path)
    with wave.open(out_path, "wb") as wav:
        header_written = False
        for chunk in voice.synthesize(naturalize_text(text), syn_config=_pace_config()):
            if not header_written:
                wav.setnchannels(chunk.sample_channels)
                wav.setsampwidth(chunk.sample_width)
                wav.setframerate(chunk.sample_rate)
                header_written = True
            pcm = (np.clip(chunk.audio_float_array, -1, 1) * 32767).astype(np.int16)
            wav.writeframes(pcm.tobytes())
    return out_path


def synthesize_bytes(text, voice_path: str = None) -> bytes:
    """Generate speech for `text` in memory as WAV (Piper)."""
    return _piper_synthesize_bytes(text, voice_path)


def _piper_synthesize_bytes(text, voice_path=None) -> bytes:
    voice = _load_voice(voice_path)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        header_written = False
        for chunk in voice.synthesize(naturalize_text(text), syn_config=_pace_config()):
            if not header_written:
                wav.setnchannels(chunk.sample_channels)
                wav.setsampwidth(chunk.sample_width)
                wav.setframerate(chunk.sample_rate)
                header_written = True
            pcm = (np.clip(chunk.audio_float_array, -1, 1) * 32767).astype(np.int16)
            wav.writeframes(pcm.tobytes())
    return buf.getvalue()


# Clear, natural Indian-English female voice (Microsoft Edge neural TTS).
EDGE_VOICE = "en-IN-NeerjaNeural"


def synthesize_with_format(text, voice_path: str = None):
    """Return (audio_bytes, mime). Prefers edge-tts; Piper fallback if offline."""
    try:
        import asyncio
        import edge_tts

        async def _stream():
            c = edge_tts.Communicate(naturalize_text(text), EDGE_VOICE)
            buf = io.BytesIO()
            async for chunk in c.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            return buf.getvalue()

        return asyncio.run(_stream()), "audio/mpeg"
    except Exception:
        return _piper_synthesize_bytes(text, voice_path), "audio/wav"

