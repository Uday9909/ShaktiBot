"""Speech-to-text: sounddevice push-to-talk recording + faster-whisper.

Usage: start_recording(frames) ... stop_recording(frames) -> wav path -> transcribe(path).
"""
import tempfile
import wave
from functools import lru_cache

import numpy as np
import sounddevice as sd

from . import config

_stream = None


def start_recording(frames, samplerate=config.SAMPLE_RATE):
    """Begin capturing mono float32 audio into the caller-owned `frames` list."""
    global _stream

    def _callback(indata, frames_count, time_info, status):
        frames.append(indata[:, 0].copy())

    _stream = sd.InputStream(
        samplerate=samplerate, channels=1, dtype="float32", blocksize=2048, callback=_callback
    )
    _stream.start()


def stop_recording(frames, samplerate=config.SAMPLE_RATE):
    """Stop capture and write frames to a temp 16-bit WAV. Returns path or None."""
    global _stream
    if _stream is not None:
        try:
            _stream.stop()
        finally:
            _stream.close()
            _stream = None
    if not frames:
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
