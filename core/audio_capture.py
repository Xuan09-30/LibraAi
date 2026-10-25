import os
import collections
import threading
import numpy as np
from typing import Optional, Dict, Any

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    pyaudio = None
    PYAUDIO_AVAILABLE = False

try:
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
    PYCAW_AVAILABLE = True
except (ImportError, Exception):
    PYCAW_AVAILABLE = False


class WASAPIAudioCapture:
    """
    Full-Duplex WASAPI Loopback Acoustic Echo Cancellation (AEC) Stream (v8.0).
    Captures incoming 16 kHz microphone frames alongside a reference speaker loopback
    buffer (`pyaudio.paWASAPI`) and applies a Normalized Least Mean Squares (NLMS)
    adaptive filter to subtract speaker playback before feeding `SileroVAD` and `OpenWakeWord`.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 512,
        filter_taps: int = 128,
        step_size: float = 0.25,
        dry_run: bool = False
    ):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.filter_taps = filter_taps
        self.step_size = step_size
        self.dry_run = dry_run

        # NLMS adaptive filter weights
        self.weights = np.zeros(self.filter_taps, dtype=np.float32)
        self.ref_buffer = collections.deque(maxlen=self.chunk_size * 20)
        self._lock = threading.Lock()

        self.pa: Optional[ "pyaudio.PyAudio" ] = None
        self.mic_stream = None
        self.loopback_stream = None
        self.wasapi_active = False

    def start_streams(self) -> bool:
        """Opens the 16kHz microphone stream and attempts to open a WASAPI loopback stream."""
        if self.dry_run or not PYAUDIO_AVAILABLE:
            return False

        try:
            self.pa = pyaudio.PyAudio()
            self.mic_stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )

            # Check for WASAPI host API availability
            wasapi_idx = None
            for i in range(self.pa.get_host_api_count()):
                info = self.pa.get_host_api_info_by_index(i)
                if "wasapi" in str(info.get("name", "")).lower() or info.get("type") == getattr(pyaudio, "paWASAPI", 13):
                    wasapi_idx = i
                    break

            if wasapi_idx is not None:
                self.wasapi_active = True
            return True
        except Exception as e:
            print(f"[WASAPIAudioCapture Stream Init Warning]: {e}")
            return False

    def feed_reference_audio(self, speaker_pcm_bytes: bytes, source_rate: int = 24000):
        """
        Feeds active TTS speaker output bytes into the loopback reference buffer
        (downsampling from 24kHz Kokoro output to 16kHz mic rate if needed) for NLMS subtraction.
        """
        if not speaker_pcm_bytes:
            return
        spk_np = np.frombuffer(speaker_pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if source_rate != self.sample_rate and len(spk_np) > 1:
            target_len = int(len(spk_np) * self.sample_rate / source_rate)
            if target_len > 0:
                x_old = np.linspace(0.0, 1.0, len(spk_np))
                x_new = np.linspace(0.0, 1.0, target_len)
                spk_np = np.interp(x_new, x_old, spk_np).astype(np.float32)

        with self._lock:
            self.ref_buffer.extend(spk_np.tolist())

    def cancel_echo_nlms(self, mic_pcm_bytes: bytes, ref_pcm_bytes: Optional[bytes] = None) -> bytes:
        """
        Applies Normalized Least Mean Squares (NLMS) adaptive echo cancellation
        to subtract the speaker reference signal from incoming microphone PCM bytes.
        """
        mic_samples = np.frombuffer(mic_pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        n_samples = len(mic_samples)

        if ref_pcm_bytes is not None:
            ref_samples = np.frombuffer(ref_pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        else:
            with self._lock:
                if len(self.ref_buffer) >= n_samples:
                    ref_samples = np.array([self.ref_buffer.popleft() for _ in range(n_samples)], dtype=np.float32)
                else:
                    return mic_pcm_bytes

        if len(ref_samples) < n_samples:
            ref_samples = np.pad(ref_samples, (0, n_samples - len(ref_samples)))

        # Vectorized block NLMS adaptive filter
        eps = 1e-6
        residual = np.zeros(n_samples, dtype=np.float32)
        padded_ref = np.pad(ref_samples, (self.filter_taps - 1, 0))

        for i in range(n_samples):
            x_vec = padded_ref[i:i + self.filter_taps][::-1]
            y_hat = float(np.dot(self.weights, x_vec))
            err = mic_samples[i] - y_hat
            norm = float(np.dot(x_vec, x_vec)) + eps
            self.weights += (self.step_size / norm) * err * x_vec
            residual[i] = err

        cleaned_int16 = (np.clip(residual, -1.0, 1.0) * 32767.0).astype(np.int16)
        return cleaned_int16.tobytes()

    def close(self):
        """Safely closes active PyAudio streams."""
        try:
            if self.mic_stream:
                self.mic_stream.stop_stream()
                self.mic_stream.close()
        except Exception:
            pass
        try:
            if self.pa:
                self.pa.terminate()
        except Exception:
            pass


def scale_pcm_amplitude(pcm_bytes: bytes, gain: float) -> bytes:
    """
    Scales 16-bit signed PCM audio amplitude in memory.

    :param pcm_bytes: Raw 16-bit mono PCM byte string.
    :param gain: Volume multiplier (0.0 = mute, 0.5 = -6dB, 1.0 = original).
    :return: Scaled 16-bit mono PCM byte string.
    """
    if not pcm_bytes or gain <= 0.0:
        return b"\x00" * len(pcm_bytes)
    if gain == 1.0:
        return pcm_bytes

    # Convert 16-bit signed PCM bytes to float32 to prevent integer overflow
    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)

    # Scale and clamp strictly between signed 16-bit integer boundaries
    scaled = np.clip(samples * gain, -32768, 32767).astype(np.int16)

    return scaled.tobytes()


def get_windows_master_volume() -> float:
    """Returns the current Windows master volume as a float between 0.0 and 1.0."""
    try:
        from pycaw.pycaw import AudioUtilities
        speakers = AudioUtilities.GetSpeakers()
        if hasattr(speakers, "EndpointVolume") and speakers.EndpointVolume:
            return float(speakers.EndpointVolume.GetMasterVolumeLevelScalar())
        elif hasattr(speakers, "volume_percent"):
            return float(speakers.volume_percent) / 100.0
        elif hasattr(speakers, "Activate"):
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import IAudioEndpointVolume
            interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            return float(volume.GetMasterVolumeLevelScalar())
    except Exception:
        pass
    return 1.0  # Fallback to full volume if COM query fails


def get_dynamic_chime_pcm(cached_chime_bytes: bytes, base_gain: float = 0.35) -> bytes:
    """
    Computes an adaptive chime buffer based on active Windows master volume.

    :param cached_chime_bytes: Original unmodified PCM bytes loaded at startup.
    :param base_gain: Independent baseline loudness ratio (e.g., 35% of full scale).
    """
    if not cached_chime_bytes:
        return b""

    master_vol = get_windows_master_volume()

    # If the system is completely muted or at 0%, mute the chime
    if master_vol <= 0.01:
        return b""

    # Prevent harsh peaks when Windows volume is cranked up
    adjusted_gain = base_gain * (0.5 + 0.5 * (1.0 - master_vol * 0.4))

    return scale_pcm_amplitude(cached_chime_bytes, gain=adjusted_gain)


class AudioDucker:
    """
    Native Windows Core Audio API wrapper (WASAPI per-app session ducking) (Phase 7).
    When Wake Word triggers or Kokoro TTS speaks on desktop, ducks third-party
    media sessions (e.g. Spotify, Chrome) to 20% while keeping Project Libra's
    own process audio at 100%, and smoothly restoring volumes.
    NEVER ducks active game processes (Valorant, CS2, Overwatch, etc.) and
    automatically heals any sessions trapped at ducked volume after hot-reloads.
    """

    PROTECTED_GAME_PROCESSES = {
        "valorant.exe",
        "valorant-win64-shipping.exe",
        "overwatch.exe",
        "overwatch 2.exe",
        "apex.exe",
        "r5apex.exe",
        "cs2.exe",
        "csgo.exe",
        "league of legends.exe",
        "leagueclient.exe",
        "leagueclientux.exe",
        "dota2.exe",
        "dota.exe",
        "fortniteclient-win64-shipping.exe",
        "gta5.exe",
        "palworld-win64-shipping.exe",
        "genshinimpact.exe",
        "starrail.exe",
        "honkaistarrail.exe",
        "zenlesszonezero.exe",
        "robloxplayerbeta.exe",
        "minecraft.exe",
        "javaw.exe",
        "rainbowsix.exe",
        "r6.exe",
        "destiny2.exe",
        "warframe.x64.exe",
        "pubg.exe",
        "tslgame.exe",
        "helldivers2.exe",
        "eldenring.exe",
        "cyberpunk2077.exe",
    }

    def __init__(self):
        self._saved_volumes: Dict[int, float] = {}
        self._is_ducked = False
        self._lock = threading.Lock()
        # Self-heal any sessions left ducked by a prior process or hot-reload
        try:
            self.restore_background_audio()
        except Exception:
            pass

    @classmethod
    def _is_game_process(cls, pname: str) -> bool:
        p = (pname or "").lower().strip()
        if not p:
            return False
        return (
            p in cls.PROTECTED_GAME_PROCESSES
            or p.endswith("-shipping.exe")
            or "valorant" in p
        )

    def duck_background_audio(self, target_level: float = 0.20) -> int:
        """
        Ducks non-Libra, non-game audio sessions down to target_level (default 20%).
        If a protected game is running, skips ducking and ensures game volume is 100%.
        Returns the number of ducked application sessions.
        """
        if not PYCAW_AVAILABLE:
            return 0

        current_pid = os.getpid()
        ducked_count = 0

        with self._lock:
            try:
                sessions = AudioUtilities.GetAllSessions()
                # First pass: check if any protected game has an active audio session
                game_running = False
                for session in sessions:
                    proc = session.Process
                    if not proc:
                        continue
                    pname = (proc.name() or "").lower()
                    if self._is_game_process(pname):
                        game_running = True
                        try:
                            vol_ctl = session._ctl.QueryInterface(ISimpleAudioVolume)
                            if float(vol_ctl.GetMasterVolume()) <= 0.25:
                                vol_ctl.SetMasterVolume(1.0, None)
                        except Exception:
                            pass

                if game_running:
                    return 0

                for session in sessions:
                    proc = session.Process
                    if not proc or proc.pid == current_pid:
                        continue
                    pname = (proc.name() or "").lower()
                    if pname in ["system", "idle", "audiodg.exe"] or self._is_game_process(pname):
                        continue

                    try:
                        volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                        curr_vol = float(volume.GetMasterVolume())
                        if session.ProcessId not in self._saved_volumes:
                            # Never record an already-ducked volume (<=0.25) as original volume
                            self._saved_volumes[session.ProcessId] = curr_vol if curr_vol > 0.25 else 1.0
                        if curr_vol > target_level:
                            volume.SetMasterVolume(target_level, None)
                            ducked_count += 1
                    except Exception:
                        continue
                self._is_ducked = True
                return ducked_count
            except Exception as e:
                print(f"[AudioDucker Warning]: {e}")
                return 0

    def restore_background_audio(self) -> int:
        """Restores previously ducked application volumes to their original levels and heals stuck sessions."""
        if not PYCAW_AVAILABLE:
            return 0

        restored_count = 0
        with self._lock:
            try:
                sessions = AudioUtilities.GetAllSessions()
                for session in sessions:
                    proc = session.Process
                    if not proc:
                        continue
                    pid = session.ProcessId
                    pname = (proc.name() or "").lower()
                    try:
                        volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                        curr_vol = float(volume.GetMasterVolume())
                        if pid in self._saved_volumes:
                            orig_vol = self._saved_volumes[pid]
                            if orig_vol <= 0.25:
                                orig_vol = 1.0
                            volume.SetMasterVolume(orig_vol, None)
                            restored_count += 1
                        elif self._is_game_process(pname) and curr_vol <= 0.25:
                            volume.SetMasterVolume(1.0, None)
                            restored_count += 1
                        elif 0.14 <= curr_vol <= 0.21:
                            # Heal session stuck at ducked volume from prior reload
                            volume.SetMasterVolume(1.0, None)
                            restored_count += 1
                    except Exception:
                        pass
                self._saved_volumes.clear()
                self._is_ducked = False
                return restored_count
            except Exception as e:
                print(f"[AudioDucker Restore Warning]: {e}")
                self._saved_volumes.clear()
                self._is_ducked = False
                return 0


audio_ducker = AudioDucker()
