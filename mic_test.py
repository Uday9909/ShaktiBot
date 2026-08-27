"""Quick mic diagnostic — prints live RMS values for 5 seconds.

Run:  python mic_test.py

Look at the output:
  - "Ambient" lines (when you're quiet) → this is your noise floor
  - "Speech" lines (when you talk)     → this is your signal level

The SILENCE_THRESHOLD in stt.py must sit between these two numbers.
"""
import time
import numpy as np
import sounddevice as sd

try:
    dev = sd.query_devices(kind="input")
    sr = int(dev["default_samplerate"])
    print(f"Input device : {dev['name']}")
    print(f"Sample rate  : {sr}")
except Exception as e:
    print(f"Could not query input device: {e}")
    sr = 16000

print("\n--- Recording 5 seconds. Stay silent for 2s, then speak. ---\n")

rms_values = []

def callback(indata, frames, time_info, status):
    rms = float(np.sqrt(np.mean(indata[:, 0] ** 2)))
    rms_values.append(rms)
    bar = "█" * int(min(rms * 500, 60))
    print(f"  RMS: {rms:.6f}  {bar}")

stream = sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                        blocksize=2048, callback=callback)
stream.start()
time.sleep(5)
stream.stop()
stream.close()

if rms_values:
    arr = np.array(rms_values)
    print(f"\n--- Summary ---")
    print(f"  Min RMS  : {arr.min():.6f}")
    print(f"  Max RMS  : {arr.max():.6f}")
    print(f"  Mean RMS : {arr.mean():.6f}")
    print(f"  Median   : {np.median(arr):.6f}")
    print(f"\nRecommended SILENCE_THRESHOLD ≈ {np.median(arr) * 3:.4f}")
    print(f"(Current value in stt.py is 0.01)")
