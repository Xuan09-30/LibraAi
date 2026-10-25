import time
import collections
from typing import List, Union
import numpy as np


class WakeWordBooster:
    """
    Wake-Word Sensitivity Booster, AGC & Continuous Follow-Up Manager.
    Aligns 512-sample VAD audio chunks into 1280-sample frames for OpenWakeWord,
    applies dynamic Automatic Gain Control (AGC) for distant/quiet voices,
    enables VAD-assisted adaptive thresholding, and maintains a pre-roll ring buffer
    along with a 6-second continuous follow-up conversation window.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        target_frame_size: int = 1280,
        default_threshold: float = 0.50,
        vad_assisted_threshold: float = 0.32,
        gaming_threshold: float = 0.78,
        preroll_max_chunks: int = 32
    ):
        self.sample_rate = sample_rate
        self.target_frame_size = target_frame_size
        self.default_threshold = default_threshold
        self.vad_assisted_threshold = vad_assisted_threshold
        self.gaming_threshold = gaming_threshold
        self.is_game_mode: bool = False
        self.consecutive_hits: int = 0
        self.accumulator = np.array([], dtype=np.int16)
        self.preroll_buffer = collections.deque(maxlen=preroll_max_chunks)
        self.followup_until_epoch: float = 0.0

    def set_game_mode(self, active: bool):
        """Toggles anti-false-positive gaming shield mode."""
        self.is_game_mode = bool(active)
        if self.is_game_mode:
            self.consecutive_hits = 0
            self.clear_followup_window()

    @property
    def remainder_buffer(self) -> np.ndarray:
        """Returns the remaining un-sliced samples in the accumulator."""
        return self.accumulator

    def apply_agc(self, frame: np.ndarray) -> np.ndarray:
        """
        Software Automatic Gain Control (AGC).
        If signal is above noise floor (rms > 150) but quiet (peak < 12000),
        amplifies signal with dynamic gain (capped at 3.5x) without clipping [-32768, 32767].
        """
        if len(frame) == 0:
            return frame

        # If gaming mode active, suppress AGC amplification to avoid boosting teammate Discord voices
        if self.is_game_mode:
            return frame

        peak = float(np.max(np.abs(frame)))
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))

        if rms > 150.0 and peak < 12000.0:
            # Target peak amplitude around 20,000 for neural model feature extraction
            target_peak = 20000.0
            gain = min(3.5, target_peak / max(peak, 1.0))
            gain = max(1.0, gain)
            amplified = np.clip(frame.astype(np.float32) * gain, -32768, 32767).astype(np.int16)
            return amplified

        return frame

    def process_chunk(
        self,
        chunk: Union[bytes, np.ndarray],
        apply_agc: bool = True
    ) -> List[np.ndarray]:
        """
        Accumulates incoming chunks (e.g. 512 samples) and slices into 1280-sample frames.
        Appends chunk to pre-roll deque and applies AGC to emitted frames if enabled.
        """
        if isinstance(chunk, bytes):
            chunk_bytes = chunk
            chunk_np = np.frombuffer(chunk, dtype=np.int16)
        else:
            chunk_np = chunk.astype(np.int16)
            chunk_bytes = chunk_np.tobytes()

        # Save to 1.0s pre-roll ring buffer
        self.preroll_buffer.append(chunk_bytes)

        # Accumulate
        if len(self.accumulator) == 0:
            self.accumulator = chunk_np
        else:
            self.accumulator = np.concatenate([self.accumulator, chunk_np])

        frames: List[np.ndarray] = []
        while len(self.accumulator) >= self.target_frame_size:
            slice_frame = self.accumulator[:self.target_frame_size]
            self.accumulator = self.accumulator[self.target_frame_size:]

            if apply_agc:
                slice_frame = self.apply_agc(slice_frame)

            frames.append(slice_frame)

        return frames

    def add_chunk(self, chunk: Union[bytes, np.ndarray], apply_agc: bool = True) -> List[np.ndarray]:
        """Alias for process_chunk."""
        return self.process_chunk(chunk, apply_agc=apply_agc)

    def get_threshold(self, vad_prob: float = 0.0, in_game: Union[bool, None] = None) -> float:
        """
        Returns dynamic wake-word threshold.
        In game mode, enforces elevated gaming_threshold (0.78) to eliminate ambient voice chat triggers.
        In desktop mode, uses vad_assisted_threshold when human speech is active.
        """
        active_game = self.is_game_mode if in_game is None else in_game
        if active_game:
            return self.gaming_threshold
        if vad_prob >= 0.35:
            return self.vad_assisted_threshold
        return self.default_threshold

    def is_wakeword_triggered(self, score: float, vad_prob: float = 0.0, in_game: Union[bool, None] = None) -> bool:
        """
        Checks if detection score satisfies dynamic threshold.
        When in gaming mode, requires multi-frame verification (>=2 consecutive frames meeting gaming threshold
        or a single definitive score >= 0.88) to filter out transient phonemes from normal conversational speech.
        """
        active_game = self.is_game_mode if in_game is None else in_game
        thresh = self.get_threshold(vad_prob=vad_prob, in_game=active_game)
        if active_game:
            if score >= thresh:
                self.consecutive_hits += 1
            else:
                self.consecutive_hits = 0

            if self.consecutive_hits >= 2 or score >= 0.88:
                self.consecutive_hits = 0
                return True
            return False
        else:
            return score >= thresh

    def set_followup_window(self, duration_sec: float = 6.0):
        """Sets the active conversational follow-up window."""
        self.followup_until_epoch = time.time() + duration_sec

    def is_in_followup_window(self) -> bool:
        """Checks if current time is within the conversational follow-up window."""
        return time.time() < self.followup_until_epoch

    def clear_followup_window(self):
        """Cancels any remaining follow-up window."""
        self.followup_until_epoch = 0.0

    def get_preroll_audio(self) -> np.ndarray:
        """Returns concatenated pre-roll audio as float32 in [-1.0, 1.0]."""
        if not self.preroll_buffer:
            return np.array([], dtype=np.float32)
        all_bytes = b"".join(self.preroll_buffer)
        return np.frombuffer(all_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    def get_preroll_chunks(self) -> List[bytes]:
        """Returns raw bytes list from pre-roll buffer."""
        return list(self.preroll_buffer)

    def clear_preroll(self):
        """Clears the pre-roll ring buffer."""
        self.preroll_buffer.clear()

    def reset(self):
        """Resets sample accumulator, pre-roll buffer, and consecutive frame hits."""
        self.accumulator = np.array([], dtype=np.int16)
        self.preroll_buffer.clear()
        self.consecutive_hits = 0
