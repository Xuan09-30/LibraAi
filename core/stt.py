import os
import re
import numpy as np

try:
    from faster_whisper import WhisperModel
    USE_FASTER_WHISPER = True
except ImportError:
    import whisper
    USE_FASTER_WHISPER = False


class SpeechToText:
    def __init__(self, model_size="small.en", device="auto", compute_type="default"):
        print(f"[STT] Loading Whisper STT model ({model_size})...")
        self.use_faster = USE_FASTER_WHISPER

        if self.use_faster:
            dev = "cuda" if device == "cuda" else "cpu"
            comp = "float16" if dev == "cuda" else "int8"
            self.model = WhisperModel(model_size, device=dev, compute_type=comp)
        else:
            self.model = whisper.load_model(model_size)

        print("[STT] Speech-to-Text engine ready.")

    def transcribe(self, audio_data: np.ndarray) -> str:
        if audio_data is None or len(audio_data) == 0:
            return ""

        # Peak normalization
        max_val = np.max(np.abs(audio_data))
        if max_val > 0.01:
            audio_data = audio_data / max_val * 0.95

        # Subtle acoustic prompt to guide proper noun phonetics
        prompt_context = "Esports players, gaming, tech, and software commands."

        text = ""
        if self.use_faster:
            segments, info = self.model.transcribe(
                audio_data,
                beam_size=5,
                initial_prompt=prompt_context,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300),
                no_speech_threshold=0.5
            )
            text = " ".join([seg.text for seg in segments]).strip()
        else:
            result = self.model.transcribe(
                audio_data, 
                fp16=False, 
                initial_prompt=prompt_context,
                no_speech_threshold=0.5
            )
            text = result.get("text", "").strip()

        repetitions = re.findall(r'(\b[\w\s\']+\b)(?:\s*,\s*\1){2,}', text, re.IGNORECASE)
        if repetitions:
            return ""

        return text