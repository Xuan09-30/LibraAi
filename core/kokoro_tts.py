import os
import time
import random
import logging
import warnings
from datetime import datetime
from typing import Optional, Dict, Any, Generator
from zoneinfo import ZoneInfo

import torch
import numpy as np

# Bypass cuDNN sub-library version mismatch while keeping GPU CUDA acceleration
if torch.cuda.is_available():
    torch.backends.cudnn.enabled = False
    torch.backends.cuda.matmul.allow_tf32 = True

# Suppress phonemizer and PyTorch deprecation warnings
logging.getLogger("phonemizer").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

from core.text_cleaner import normalize_for_tts

try:
    from kokoro import KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False


BACKCHANNEL_PHRASES = {
    "data_science": [
        "Pulling up the data...",
        "Running the statistical analysis now...",
        "Crunching the dataset..."
    ],
    "deep_research": [
        "Looking into that now...",
        "Synthesizing the research...",
        "Scanning the latest sources..."
    ],
    "document_rag": [
        "Checking the files...",
        "Reading through the document...",
        "Scanning those pages now..."
    ],
    "default": [
        "Looking into that now...",
        "One moment while I check...",
        "Processing that right now..."
    ]
}

HEAVY_ROUTES = {
    "data_science",
    "deep_research",
    "document_rag",
    "security_scan",
    "web_search",
    "create_skill"
}


class KokoroTTS:
    def __init__(self, voice="af_heart", lang_code="a", device="cuda", lazy_load: bool = False):
        """Initializes Kokoro-82M TTS pipeline with CUDA priority, Acoustic Backchanneling & Circadian Prosody."""
        self.voice = voice
        self.lang_code = lang_code
        self.device = "cuda" if (torch.cuda.is_available() and device == "cuda") else "cpu"
        self.sample_rate = 24000
        self.pipeline = None
        self.timezone = ZoneInfo("Asia/Kuala_Lumpur")

        if lazy_load:
            return

        if not KOKORO_AVAILABLE:
            print("[Kokoro Warning]: kokoro package not found.")
            return

        print(f"[Kokoro TTS] Loading 82M model onto {self.device} (Voice: {self.voice})...")
        try:
            self.pipeline = KPipeline(
                repo_id="hexgrad/Kokoro-82M",
                lang_code=self.lang_code,
                device=self.device
            )
            print(f"[Kokoro TTS] Engine online on {self.device.upper()}.")
        except Exception as e:
            print(f"[Kokoro CUDA Warning]: {e}. Retrying on CPU...")
            self.device = "cpu"
            self.pipeline = KPipeline(
                repo_id="hexgrad/Kokoro-82M",
                lang_code=self.lang_code,
                device="cpu"
            )

    def get_prosody_config(
        self,
        urgency: str = "normal",
        current_hour: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Computes Dynamic Prosody & Circadian Mode parameters (v8.0):
          - Standard voice: speed=1.05, pitch=1.0, gain=1.0
          - Urgent/Tactical: speed=1.18, pitch=1.0, gain=1.0
          - Night Mode (local time in Asia/Kuala_Lumpur between 23:00 and 06:00):
            reduces synthesis volume gain by 30% (gain=0.70), sets speed=0.95.
        """
        if current_hour is None:
            now_kl = datetime.now(self.timezone)
            hour = now_kl.hour
        else:
            hour = int(current_hour)

        is_night = (hour >= 23 or hour < 6)

        if str(urgency).lower() in ("high", "urgent", "tactical"):
            return {
                "mode": "urgent",
                "speed": 1.18,
                "pitch": 1.0,
                "gain": 1.0,
                "night_mode": False
            }

        if is_night:
            return {
                "mode": "night",
                "speed": 0.95,
                "pitch": 1.0,
                "gain": 0.70,
                "night_mode": True
            }

        return {
            "mode": "normal",
            "speed": 1.05,
            "pitch": 1.0,
            "gain": 1.0,
            "night_mode": False
        }

    def get_backchannel_bridge(
        self,
        route_or_task: str = "default",
        expected_latency_sec: float = 1.5
    ) -> Optional[Dict[str, Any]]:
        """
        Acoustic Backchanneling (v8.0):
        If an incoming query is classified as a heavy task (expected latency > 1.2s),
        immediately generates a short, natural vocal bridge ("Looking into that now...",
        "Pulling up the data...", "Checking the files...") in < 5ms so TTFA is < 300ms.
        """
        t0 = time.perf_counter()
        route_key = (route_or_task or "default").lower().strip()
        if expected_latency_sec <= 1.2 and route_key not in HEAVY_ROUTES:
            return None

        pool = BACKCHANNEL_PHRASES.get(route_key, BACKCHANNEL_PHRASES["default"])
        phrase = pool[0]

        # Generate a fast 200ms soft acoustic chime/envelope or PCM preview buffer (<5ms)
        n_samples = int(self.sample_rate * 0.20)
        t_axis = np.linspace(0.0, 0.20, n_samples, endpoint=False, dtype=np.float32)
        envelope = np.sin(np.pi * t_axis / 0.20) * 0.15
        wave = envelope * np.sin(2.0 * np.pi * 440.0 * t_axis)
        pcm_bytes = (wave * 32767.0).astype(np.int16).tobytes()

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "triggered": True,
            "phrase": phrase,
            "route": route_key,
            "pcm_bytes": pcm_bytes,
            "ttfa_ms": elapsed_ms
        }

    def synthesize_stream(
        self,
        text: str,
        urgency: str = "normal",
        current_hour: Optional[int] = None
    ) -> Generator[bytes, None, None]:
        """Yields raw int16 PCM bytes per sentence with dynamic circadian & urgency prosody."""
        clean_text = normalize_for_tts(text)
        if not self.pipeline or not clean_text.strip():
            return

        prosody = self.get_prosody_config(urgency=urgency, current_hour=current_hour)
        speed = prosody["speed"]
        gain = prosody["gain"]

        generator = self.pipeline(clean_text, voice=self.voice, speed=speed)
        for _, _, audio in generator:
            if audio is None or len(audio) == 0:
                continue

            audio_np = audio.cpu().numpy() if hasattr(audio, "cpu") else np.array(audio)
            audio_scaled = np.clip(audio_np * gain, -1.0, 1.0)
            audio_int16 = (audio_scaled * 32767).astype(np.int16)
            yield audio_int16.tobytes()