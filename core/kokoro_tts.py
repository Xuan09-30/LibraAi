import os
import warnings
import torch
import numpy as np

# Suppress PyTorch deprecation warnings to keep the worker logs clean
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

try:
    from kokoro import KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False


class KokoroTTS:
    def __init__(self, voice="af_heart", lang_code="a", device="cuda"):
        """Initializes Kokoro-82M TTS pipeline.

        Voices:
        - af_heart (warm, natural female)
        - af_bella, af_sarah, af_sky
        - am_adam, am_michael (male)
        """
        self.voice = voice
        self.lang_code = lang_code
        self.device = "cuda" if (torch.cuda.is_available() and device == "cuda") else "cpu"
        self.sample_rate = 24000
        self.pipeline = None

        if not KOKORO_AVAILABLE:
            print("[Kokoro Warning]: kokoro package not found.")
            return

        print(f"[Kokoro TTS] Loading 82M model onto {self.device} (Voice: {self.voice})...")
        try:
            # Explicitly specify repo_id to prevent Hugging Face default warning
            self.pipeline = KPipeline(
                repo_id="hexgrad/Kokoro-82M",
                lang_code=self.lang_code,
                device=self.device
            )
            print(f"[Kokoro TTS] Engine online on {self.device}.")
        except Exception as e:
            print(f"[Kokoro Init Error]: {e}. Falling back to CPU...")
            self.device = "cpu"
            self.pipeline = KPipeline(
                repo_id="hexgrad/Kokoro-82M",
                lang_code=self.lang_code,
                device="cpu"
            )

    def synthesize_stream(self, text: str):
        """Yields raw int16 PCM bytes per sentence for low-latency streaming playback."""
        if not self.pipeline or not text.strip():
            return

        generator = self.pipeline(text, voice=self.voice, speed=1.0)
        for _, _, audio in generator:
            if audio is None or len(audio) == 0:
                continue

            audio_np = audio.cpu().numpy() if hasattr(audio, "cpu") else np.array(audio)
            audio_int16 = (np.clip(audio_np, -1.0, 1.0) * 32767).astype(np.int16)
            yield audio_int16.tobytes()