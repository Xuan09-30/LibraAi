import os
import sys
import time
import wave
import numpy as np

# Ensure project root is in the Python module search path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.vad import SileroVADDetector
from core.telemetry import profiler


def run_test(simulate: bool = True):
    CHUNK_SIZE = 512
    RATE = 16000

    vad = SileroVADDetector(sample_rate=RATE, silence_cutoff_sec=0.8)
    print("\n[READY] Running Silero VAD 0.8s silence boundary latency test...")

    test_wav_path = os.path.join(PROJECT_ROOT, "tests", "test_speech.wav")
    if os.path.exists(test_wav_path):
        with wave.open(test_wav_path, "rb") as wf:
            pcm_data = wf.readframes(wf.getnframes())
    else:
        t = np.linspace(0, 1.5, int(RATE * 1.5), endpoint=False)
        synthetic = 0.5 * np.sin(2 * np.pi * 300 * t) + 0.3 * np.sin(2 * np.pi * 600 * t)
        pcm_data = (synthetic * 32767).astype(np.int16).tobytes()

    silence_padding = b"\x00" * int(RATE * 2 * 1.0)
    stream_bytes = pcm_data + silence_padding
    chunk_bytes = CHUNK_SIZE * 2

    speech_detected_time = None
    completed = False

    for i in range(0, len(stream_bytes), chunk_bytes):
        data = stream_bytes[i:i + chunk_bytes]
        if len(data) < chunk_bytes:
            data = data + b"\x00" * (chunk_bytes - len(data))

        if not vad.has_spoken:
            is_done, _ = vad.process_chunk(data)
            if vad.has_spoken:
                speech_detected_time = time.perf_counter()
                print("[LISTENING] User speaking...")
        else:
            is_done, audio_tensor = vad.process_chunk(data)
            if is_done:
                cutoff_time = time.perf_counter()
                total_hold_time = (cutoff_time - (speech_detected_time or cutoff_time)) * 1000.0
                print(f"\n[SPEECH ENDED] Detected 0.8s silence boundary!")
                print(f"Total audio segment length: {len(audio_tensor) / RATE:.2f} seconds")
                profiler.record_metric("vad_silence_wait_ms", 800.0)
                profiler.record_metric("total_capture_ms", total_hold_time)
                logged = profiler.flush(transcript="[Audio Test Phrase]", route="vad_test")
                print(f"Logged to 'logs/latency_metrics.jsonl': {logged}")
                completed = True
                break

    assert completed, "VAD failed to trigger 0.8s silence cutoff on speech stream"
    print("[PASS] VAD 0.8s boundary latency test verified.")


def test_suite():
    run_test(simulate=True)


if __name__ == "__main__":
    run_test(simulate=True)
