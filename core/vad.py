import numpy as np
import torch

class SileroVADDetector:
    def __init__(self, sample_rate: int = 16000, silence_cutoff_sec: float = 0.8):
        self.sample_rate = sample_rate
        self.silence_cutoff_sec = silence_cutoff_sec
        # 512 samples at 16kHz = 32ms per frame
        self.frame_samples = 512
        self.max_silence_frames = int(silence_cutoff_sec / (self.frame_samples / self.sample_rate))
        
        # Load ONNX-optimized Silero VAD
        self.model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            onnx=True,
            trust_repo=True
        )
        self.reset()

    def reset(self):
        self.consecutive_silence = 0
        self.has_spoken = False
        self.audio_buffer = []

    def process_chunk(self, pcm_16k_int16: bytes) -> tuple[bool, np.ndarray | None]:
        """
        Accepts 512 samples of 16-bit mono PCM.
        Returns: (is_utterance_complete, full_audio_float32_or_None)
        """
        # Convert int16 bytes to normalized float32 tensor
        chunk = np.frombuffer(pcm_16k_int16, dtype=np.int16).astype(np.float32) / 32768.0
        tensor = torch.from_numpy(chunk)

        # Silero VAD forward pass
        speech_prob = self.model(tensor, self.sample_rate).item()
        is_speech = speech_prob >= 0.50

        if is_speech:
            self.has_spoken = True
            self.consecutive_silence = 0
            self.audio_buffer.append(chunk)
            return False, None

        if self.has_spoken:
            self.consecutive_silence += 1
            self.audio_buffer.append(chunk)
            
            # Hit the 0.8s silence window
            if self.consecutive_silence >= self.max_silence_frames:
                full_audio = np.concatenate(self.audio_buffer, axis=0)
                self.reset()
                return True, full_audio

        return False, None