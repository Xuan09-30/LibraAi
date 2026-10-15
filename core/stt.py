import os
import sys
import re
import importlib
import numpy as np

# On Windows (Python 3.8+), DLLs from pip packages must be registered via os.add_dll_directory
def register_cuda_dlls():
    if sys.platform == "win32":
        # Search inside site-packages for torch/lib and nvidia CUDA/cuDNN DLL directories
        site_packages = [p for p in sys.path if "site-packages" in p]
        for sp in site_packages:
            torch_lib = os.path.join(sp, "torch", "lib")
            if os.path.isdir(torch_lib):
                try:
                    os.add_dll_directory(torch_lib)
                    os.environ["PATH"] = torch_lib + os.pathsep + os.environ.get("PATH", "")
                except Exception:
                    pass
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
    def __init__(
        self,
        model_size: str = "large-v3-turbo",
        device: str = "cuda",
        compute_type: str = "float16",
        initial_prompt: str = "Libra, Valorant, Riot, Steam, Fernando Alonso, Kepong, Kuala Lumpur, Qwen, benchmarks, benchmark, RTX 5070, RTX 5080, GPU, CPU, RAM, VRAM, Nvidia, DLSS, framerate, specs, hardware."
    ):
        """Initializes Faster-Whisper on CUDA float16 with fallback."""
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.initial_prompt = initial_prompt
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

    def transcribe(self, audio_data: np.ndarray | bytes) -> str:
        if audio_data is None:
            return ""

        # Input handling: automatically convert raw int16 PCM bytes or numpy arrays into float32 normalized to [-1.0, 1.0].
        if isinstance(audio_data, (bytes, bytearray)):
            if len(audio_data) == 0:
                return ""
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        elif isinstance(audio_data, np.ndarray):
            if audio_data.size == 0:
                return ""
            audio_np = audio_data.flatten()
            if audio_np.dtype == np.int16:
                audio_np = audio_np.astype(np.float32) / 32768.0
            else:
                audio_np = audio_np.astype(np.float32)
                # Normalize if integer range scale
                max_abs = np.max(np.abs(audio_np)) if len(audio_np) > 0 else 0.0
                if max_abs > 1.0:
                    audio_np = audio_np / 32768.0
        else:
            return ""

        audio_np = np.clip(audio_np, -1.0, 1.0)
        if len(audio_np) == 0:
            return ""

        # Peak normalization and silence threshold
        max_val = np.max(np.abs(audio_np))
        if max_val < 0.005:
            return ""
        if max_val > 0.01:
            audio_np = audio_np / max_val * 0.95

        text = ""
        try:
            if self.use_faster:
                segments, info = self.model.transcribe(
                    audio_np,
                    beam_size=1,
                    language="en",
                    condition_on_previous_text=False,
                    temperature=0.0,
                    initial_prompt=self.initial_prompt,
                    vad_filter=True
                )
                seg_list = list(segments)

                # Set no_speech_prob on info if not natively present
                if not hasattr(info, "no_speech_prob"):
                    if not seg_list:
                        info.no_speech_prob = 1.0
                    else:
                        info.no_speech_prob = max((getattr(s, "no_speech_prob", 0.0) for s in seg_list), default=0.0)

                # Filter out hallucinations: if info.no_speech_prob > 0.60, return an empty string ""
                if info.no_speech_prob > 0.60:
                    return ""

                text = " ".join([seg.text for seg in seg_list]).strip()
            else:
                result = self.model.transcribe(
                    audio_np, 
                    fp16=(self.device == "cuda"),
                    beam_size=1,
                    language="en",
                    condition_on_previous_text=False,
                    temperature=0.0,
                    initial_prompt=self.initial_prompt
                )
                no_speech = result.get("no_speech_prob", 0.0)
                if no_speech > 0.60:
                    return ""
                text = result.get("text", "").strip()
        except Exception as ex:
            print(f"[STT Error]: {ex}")
            return ""

        # Filter out repetitive hallucinations
        repetitions = re.findall(r'(\b[\w\s\']+\b)(?:\s*,\s*\1){2,}', text, re.IGNORECASE)
        if repetitions:
            return ""

        # Phonetic sanitation for common Whisper acoustic confusions
        text = re.sub(r"\bbatch\s*marks\b", "benchmarks", text, flags=re.IGNORECASE)
        text = re.sub(r"\bbatch\s*mark\b", "benchmark", text, flags=re.IGNORECASE)

        return text