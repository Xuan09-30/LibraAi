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
    def __init__(self, voice="af_heart", lang_code="a"):
        # Auto-detect CUDA availability
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[Kokoro TTS] Initializing pipeline on device: {self.device} (Voice: {voice})...")
        
        # Initialize KPipeline on CUDA
        self.pipeline = KPipeline(lang_code=lang_code, device=self.device)
        self.voice = voice

    def generate_audio(self, text: str):
        """Generates raw audio chunks directly on device."""
        generator = self.pipeline(text, voice=self.voice, speed=1.0, split_pattern=r'\n+')
        audio_segments = []
        for _, _, audio in generator:
            audio_segments.append(audio)
            
        if not audio_segments:
            return None
            
        if len(audio_segments) == 1:
            return audio_segments[0]
        return torch.cat(audio_segments, dim=0)

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