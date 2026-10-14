import os
import sys

# Ensure project root is in the Python module search path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import time
import pyaudio
from core.vad import SileroVADDetector
from core.telemetry import profiler

def run_test():
    CHUNK_SIZE = 512
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000

    vad = SileroVADDetector(sample_rate=RATE, silence_cutoff_sec=0.8)
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK_SIZE)

    print("\n[READY] Speak a sentence into your microphone (e.g. 'Testing Libra latency')...")
    
    speech_detected_time = None

    try:
        while True:
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            
            # Track when user starts speaking
            if not vad.has_spoken:
                is_done, _ = vad.process_chunk(data)
                if vad.has_spoken:
                    speech_detected_time = time.perf_counter()
                    print("[LISTENING] User speaking...")
            else:
                is_done, audio_tensor = vad.process_chunk(data)
                if is_done:
                    cutoff_time = time.perf_counter()
                    total_hold_time = (cutoff_time - speech_detected_time) * 1000.0

                    print(f"\n[SPEECH ENDED] Detected 0.8s silence boundary!")
                    print(f"Total audio segment length: {len(audio_tensor) / RATE:.2f} seconds")

                    # Log latency telemetry
                    profiler.record_metric("vad_silence_wait_ms", 800.0)
                    profiler.record_metric("total_capture_ms", total_hold_time)
                    logged = profiler.flush(transcript="[Audio Test Phrase]", route="vad_test")
                    
                    print(f"Logged to 'logs/latency_metrics.jsonl': {logged}")
                    break

    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

if __name__ == "__main__":
    run_test()