import os
import sys
import re
import importlib
import numpy as np

# On Windows (Python 3.8+), DLLs from pip packages must be registered via os.add_dll_directory
def register_cuda_dlls():
    if sys.platform == "win32":
        # Search inside site-packages for nvidia CUDA/cuDNN DLL directories
        site_packages = [p for p in sys.path if "site-packages" in p]
        for sp in site_packages:
            nvidia_dir = os.path.join(sp, "nvidia")
            if os.path.isdir(nvidia_dir):
                for root, _, files in os.walk(nvidia_dir):
                    if any(f.endswith(".dll") for f in files):
                        try:
                            os.add_dll_directory(root)
                            os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")
                        except Exception:
                            pass

register_cuda_dlls()

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    try:
        whisper = importlib.import_module("whisper")
    except ImportError:
        whisper = None


class SpeechToText:
    def __init__(self, model_size="large-v3-turbo", device="cuda", compute_type="float16"):
        """Initializes Faster-Whisper on CUDA (falling back to float32 on CPU if CUDA is unavailable)."""
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.use_faster = FASTER_WHISPER_AVAILABLE

        if not self.use_faster and whisper is None:
            raise ImportError("Install faster-whisper or openai-whisper to use speech recognition.")

        print(f"[STT] Loading Whisper ({self.model_size}) on {self.device} ({self.compute_type})...")
        
        try:
            if self.use_faster:
                self.model = WhisperModel(
                    self.model_size, 
                    device=self.device, 
                    compute_type=self.compute_type
                )
            else:
                self.model = whisper.load_model(self.model_size, device=self.device)
            print("[STT] GPU Whisper engine online.")
        except Exception as e:
            print(f"[STT Warning] GPU initialization failed ({e}). Falling back to CPU...")
            self.device = "cpu"
            self.compute_type = "int8"
            if self.use_faster:
                self.model = WhisperModel("small.en", device="cpu", compute_type="int8")
            else:
                self.model = whisper.load_model("small.en", device="cpu")
            print("[STT] CPU Fallback active.")

    def transcribe(self, audio_data: np.ndarray) -> str:
        if audio_data is None or len(audio_data) == 0:
            return ""

        # Peak normalization
        max_val = np.max(np.abs(audio_data))
        if max_val > 0.01:
            audio_data = audio_data / max_val * 0.95

        # Domain priming to guide proper nouns, sports, and names
        initial_prompt = "Nikola Jokic, Max Verstappen, Lionel Messi, Lamine Yamal, Esports, Tech, Libra Assistant."

        text = ""
        try:
            if self.use_faster:
                segments, info = self.model.transcribe(
                    audio_data,
                    beam_size=5,
                    initial_prompt=initial_prompt,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=250),
                    no_speech_threshold=0.5
                )
                text = " ".join([seg.text for seg in segments]).strip()
            else:
                result = self.model.transcribe(
                    audio_data, 
                    fp16=(self.device == "cuda"),
                    initial_prompt=initial_prompt,
                    no_speech_threshold=0.5
                )
                text = result.get("text", "").strip()
        except Exception as ex:
            print(f"[STT Error]: {ex}")
            return ""

        # Filter out repetitive hallucinations
        repetitions = re.findall(r'(\b[\w\s\']+\b)(?:\s*,\s*\1){2,}', text, re.IGNORECASE)
        if repetitions:
            return ""

        return text