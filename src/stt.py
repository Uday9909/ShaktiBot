"""Speech-to-text: sounddevice push-to-talk + faster-whisper.

record_until_silence() captures audio and auto-stops when the speaker pauses,
so the caller just does: click -> speak -> it ends on its own.
"""
import tempfile
import time
import wave
from functools import lru_cache

import numpy as np
import sounddevice as sd

from . import config

SILENCE_THRESHOLD = 0.01  # RMS below this counts as silence (normalized float audio)


def _input_sample_rate():
    """Use the mic's native sample rate — Bluetooth mics (AirPods) return pure
    silence when forced to 16 kHz, but their native rate works fine."""
    try:
        return int(sd.query_devices(kind="input")["default_samplerate"])
    except Exception:
        return config.SAMPLE_RATE


def record_until_silence(frames, samplerate=None,
                         max_seconds=15.0, silence_seconds=1.2):
    """Record mono float32 audio into `frames`, stopping after `silence_seconds`
    of quiet once speech has started. Returns a temp WAV path, or None if less
    than half a second of audio was captured."""
    samplerate = samplerate or _input_sample_rate()
    state = {"start": time.monotonic(), "silence_since": None, "heard": False}

    def _callback(indata, frames_count, time_info, status):
        frames.append(indata[:, 0].copy())
        rms = float(np.sqrt(np.mean(indata[:, 0] ** 2)))
        if rms >= SILENCE_THRESHOLD:
            state["heard"] = True
            state["silence_since"] = None
        elif state["heard"] and state["silence_since"] is None:
            state["silence_since"] = time.monotonic()

    stream = sd.InputStream(samplerate=samplerate, channels=1, dtype="float32",
                            blocksize=2048, callback=_callback)
    stream.start()
    try:
        while time.monotonic() - state["start"] < max_seconds:
            if (state["heard"] and state["silence_since"]
                    and time.monotonic() - state["silence_since"] > silence_seconds):
                break
            time.sleep(0.1)
    finally:
        stream.stop()
        stream.close()

    if len(frames) < int(samplerate * 0.5):
        return None
    audio = np.concatenate(frames)
    path = tempfile.mktemp(suffix=".wav")
    write_wav(path, audio, samplerate)
    return path


def write_wav(path, audio, samplerate=config.SAMPLE_RATE):
    """Write float32 mono samples as a 16-bit PCM WAV file."""
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(pcm.tobytes())


@lru_cache(maxsize=1)
def _load_model(model_name):
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device="cpu", compute_type="int8")


def transcribe(wav_path, model_name=config.WHISPER_MODEL):
    """Transcribe a WAV file to clean text."""
    model = _load_model(model_name)
    segments, _ = model.transcribe(wav_path)
    return " ".join(s.text.strip() for s in segments).strip()
