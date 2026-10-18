import os
import wave
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def generate_cybernetic_chime(output_path=None, duration=0.075, sr=24000):
    """
    Synthesizes a 75ms cybernetic dual-frequency blip.
    Sample rate 24kHz matches Kokoro output directly to avoid audio device re-init.
    """
    if output_path is None:
        output_path = os.path.join(PROJECT_ROOT, "assets", "sounds", "chime.wav")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    # Dual-tone frequency glide: Carrier 1200Hz -> 1800Hz, harmonic at 2400Hz (1.5x)
    freq_sweep = np.linspace(1200, 1800, len(t))
    carrier = np.sin(2 * np.pi * freq_sweep * t)
    overtone = 0.4 * np.sin(2 * np.pi * (freq_sweep * 1.5) * t)
    sub = 0.2 * np.sin(2 * np.pi * (freq_sweep * 0.5) * t)

    raw_signal = carrier + overtone + sub

    # 5ms attack to prevent speaker click, sharp exponential decay (tau = 0.022s)
    attack_len = int(0.005 * sr)
    attack = np.linspace(0, 1, attack_len)
    decay = np.exp(-t / 0.022)

    envelope = decay.copy()
    envelope[:attack_len] *= attack

    # Normalize to -3 dBFS and convert to 16-bit PCM
    processed = raw_signal * envelope
    processed = processed / np.max(np.abs(processed)) * 0.70
    pcm16 = (processed * 32767).astype(np.int16)

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())

    print(f"[OK] Generated {len(pcm16)/sr*1000:.1f}ms chime at {output_path}")
    return output_path


if __name__ == "__main__":
    generate_cybernetic_chime()
