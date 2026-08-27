import io
import os
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

_voices_cache = {}


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
        for chunk in voice.synthesize(text):
            if not header_written:
                wav.setnchannels(chunk.sample_channels)
                wav.setsampwidth(chunk.sample_width)
                wav.setframerate(chunk.sample_rate)
                header_written = True
            pcm = (np.clip(chunk.audio_float_array, -1, 1) * 32767).astype(np.int16)
            wav.writeframes(pcm.tobytes())
    return out_path


def synthesize_bytes(text, voice_path: str = None) -> bytes:
    """Generate speech for `text` in memory, returning WAV bytes."""
    voice = _load_voice(voice_path)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        header_written = False
        for chunk in voice.synthesize(text):
            if not header_written:
                wav.setnchannels(chunk.sample_channels)
                wav.setsampwidth(chunk.sample_width)
                wav.setframerate(chunk.sample_rate)
                header_written = True
            pcm = (np.clip(chunk.audio_float_array, -1, 1) * 32767).astype(np.int16)
            wav.writeframes(pcm.tobytes())
    return buf.getvalue()

