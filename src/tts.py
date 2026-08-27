"""Text-to-speech via Piper.

The voice model is not bundled with the pip package — ensure_voice_downloaded()
fetches it once (or download manually, see README).
"""
import urllib.request
import wave
from pathlib import Path

import numpy as np

from . import config

VOICE_NAME = "en_US-lessac-medium"
VOICE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
    f"en/en_US/lessac/medium/{VOICE_NAME}.onnx"
)

_voice = None


def ensure_voice_downloaded() -> Path:
    """Download the Piper voice ONNX model + config if missing."""
    voice = Path(config.PIPER_VOICE)
    if voice.exists():
        return voice
    print(f"Voice model not found at {voice}. Downloading {VOICE_NAME} ...")
    voice.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(VOICE_URL, voice)
    urllib.request.urlretrieve(VOICE_URL + ".json", str(voice) + ".json")
    return voice


def _load_voice():
    global _voice
    if _voice is None:
        from piper import PiperVoice

        _voice = PiperVoice.load(str(ensure_voice_downloaded()))
    return _voice


def synthesize(text, out_path):
    """Generate speech for `text` into `out_path`. Returns the path."""
    voice = _load_voice()
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
