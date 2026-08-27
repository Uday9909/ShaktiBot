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

# Fallback silence threshold — only used if auto-calibration fails.
SILENCE_THRESHOLD_FALLBACK = 0.04

# How many times above the noise floor RMS must be to count as speech.
SPEECH_MULTIPLIER = 3.0

# Seconds of initial recording used to calibrate the ambient noise floor.
CALIBRATION_SECONDS = 0.5


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
    than half a second of audio was captured.

    The first ~0.5 s of recording is used to auto-calibrate the ambient noise
    floor so the silence/speech boundary adapts to whatever mic is active
    (built-in, AirPods, external USB, etc.).
    """
    samplerate = samplerate or _input_sample_rate()
    state = {
        "start": time.monotonic(),
        "silence_since": None,
        "heard": False,
        "threshold": SILENCE_THRESHOLD_FALLBACK,
        "calibrated": False,
        "calibration_rms": [],
    }

    def _callback(indata, frames_count, time_info, status):
        chunk = indata[:, 0].copy()
        frames.append(chunk)
        rms = float(np.sqrt(np.mean(chunk ** 2)))

        elapsed = time.monotonic() - state["start"]

        # --- Phase 1: calibration (first CALIBRATION_SECONDS) ---
        if not state["calibrated"]:
            state["calibration_rms"].append(rms)
            if elapsed >= CALIBRATION_SECONDS:
                noise_floor = float(np.median(state["calibration_rms"]))
                # Set threshold to SPEECH_MULTIPLIER × noise floor, but
                # never below the fallback (guards against dead-silent mics
                # where any click would trigger).
                state["threshold"] = max(
                    noise_floor * SPEECH_MULTIPLIER,
                    SILENCE_THRESHOLD_FALLBACK,
                )
                state["calibrated"] = True
            return  # don't evaluate speech/silence during calibration

        # --- Phase 2: speech / silence detection ---
        if rms >= state["threshold"]:
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

    total_samples = sum(len(f) for f in frames)
    if total_samples < int(samplerate * 0.5):
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
