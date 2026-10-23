import os
import sys
import time
import ctypes
from ctypes import wintypes
import threading
import collections
from typing import Optional, Callable, Any

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.text_cleaner import clean_for_dictation, DictationCleaner

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    pyaudio = None
    PYAUDIO_AVAILABLE = False

VK_RCONTROL = 0xA3
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1
VK_RETURN = 0x0D


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", INPUT_UNION),
    ]


def type_unicode_text(text: str):
    """
    Types unicode text directly into the active cursor position using Win32 SendInput.
    Handles newlines as VK_RETURN and unicode code points natively without clipboard pollution.
    """
    if not text or sys.platform != "win32":
        return

    user32 = ctypes.windll.user32
    inputs = []

    for char in text:
        if char == "\r":
            continue
        if char == "\n":
            # VK_RETURN key down
            inp_down = INPUT(type=INPUT_KEYBOARD)
            inp_down.u.ki = KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=0, time=0, dwExtraInfo=None)
            # VK_RETURN key up
            inp_up = INPUT(type=INPUT_KEYBOARD)
            inp_up.u.ki = KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
            inputs.extend([inp_down, inp_up])
        else:
            code = ord(char)
            # Unicode key down
            inp_down = INPUT(type=INPUT_KEYBOARD)
            inp_down.u.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=None)
            # Unicode key up
            inp_up = INPUT(type=INPUT_KEYBOARD)
            inp_up.u.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
            inputs.extend([inp_down, inp_up])

    if inputs:
        n_inputs = len(inputs)
        input_array = (INPUT * n_inputs)(*inputs)
        user32.SendInput(n_inputs, ctypes.byref(input_array), ctypes.sizeof(INPUT))


class WhisperDictationController:
    """
    Context-Aware Voice Typing Engine (v11.0 / Phase 11).
    Monitors global press-and-hold on VK_RCONTROL (Right Control).
    Streams 16kHz mono audio into an in-memory ring buffer (zero disk writes).
    On release, transcribes with faster-whisper, cleans with technical heuristics,
    and injects text into the foreground application via Win32 SendInput.
    """

    def __init__(
        self,
        stt_engine: Optional[Any] = None,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        on_state_change: Optional[Callable[[bool], None]] = None
    ):
        self.stt = stt_engine
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.on_state_change = on_state_change

        self._running = False
        self._is_recording = False
        self._audio_buffer = bytearray()
        self._thread: Optional[threading.Thread] = None
        self._mic_stream = None
        self._pa: Optional[pyaudio.PyAudio] = None
        self._lock = threading.Lock()

    def set_stt(self, stt_engine: Any):
        self.stt = stt_engine

    def start(self):
        """Starts the background VK_RCONTROL polling daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="DictationHookWorker")
        self._thread.start()
        print("[Dictation] Whisper Dictation Mode online (Hold Right Control to dictate).")

    def stop(self):
        """Stops the daemon thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._cleanup_audio()

    def _cleanup_audio(self):
        try:
            if self._mic_stream:
                self._mic_stream.stop_stream()
                self._mic_stream.close()
                self._mic_stream = None
        except Exception:
            pass
        try:
            if self._pa:
                self._pa.terminate()
                self._pa = None
        except Exception:
            pass

    def _init_mic(self) -> bool:
        if not PYAUDIO_AVAILABLE:
            return False
        try:
            if not self._pa:
                self._pa = pyaudio.PyAudio()
            if not self._mic_stream:
                self._mic_stream = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self.chunk_size
                )
            return True
        except Exception as e:
            print(f"[Dictation Mic Init Error]: {e}")
            return False

    def _poll_loop(self):
        if sys.platform != "win32":
            return

        user32 = ctypes.windll.user32
        was_pressed = False

        while self._running:
            # Check if VK_RCONTROL (0xA3) is pressed down (high bit set)
            state = user32.GetAsyncKeyState(VK_RCONTROL)
            is_pressed = bool(state & 0x8000)

            if is_pressed and not was_pressed:
                # Key down -> Start recording
                was_pressed = True
                self._on_key_down()

            elif not is_pressed and was_pressed:
                # Key up -> Stop recording and transcribe
                was_pressed = False
                self._on_key_up()

            if was_pressed and self._is_recording:
                # Capture chunk
                try:
                    if self._mic_stream and self._mic_stream.is_active():
                        data = self._mic_stream.read(self.chunk_size, exception_on_overflow=False)
                        with self._lock:
                            self._audio_buffer.extend(data)
                except Exception:
                    pass

            time.sleep(0.015)  # 15ms polling interval

    def _on_key_down(self):
        if not self._init_mic():
            return
        with self._lock:
            self._audio_buffer.clear()
            self._is_recording = True
        if self.on_state_change:
            try:
                self.on_state_change(True)
            except Exception:
                pass

    def _on_key_up(self):
        if not self._is_recording:
            return
        with self._lock:
            self._is_recording = False
            raw_pcm = bytes(self._audio_buffer)
            self._audio_buffer.clear()

        if self.on_state_change:
            try:
                self.on_state_change(False)
            except Exception:
                pass

        # Minimum length threshold: ~0.3s of audio (4800 samples = 9600 bytes)
        if len(raw_pcm) < 9600:
            return

        # Run transcription in a quick worker thread so we don't block polling
        threading.Thread(target=self._process_and_type, args=(raw_pcm,), daemon=True).start()

    def _process_and_type(self, raw_pcm: bytes):
        try:
            if not self.stt:
                # Lazy load STT if not passed
                from core.stt import SpeechToText
                self.stt = SpeechToText()

            raw_text = self.stt.transcribe(raw_pcm)
            if not raw_text or not raw_text.strip():
                return

            cleaned = clean_for_dictation(raw_text)
            if not cleaned:
                return

            print(f"[Dictation] Transcribed: '{raw_text}' -> Formatted: '{cleaned}'")
            # Inject directly into cursor
            type_unicode_text(cleaned)
        except Exception as e:
            print(f"[Dictation Transcription Error]: {e}")


# Singleton accessor
_dictation_instance: Optional[WhisperDictationController] = None

def get_dictation_controller(stt_engine: Optional[Any] = None) -> WhisperDictationController:
    global _dictation_instance
    if _dictation_instance is None:
        _dictation_instance = WhisperDictationController(stt_engine=stt_engine)
    elif stt_engine is not None and _dictation_instance.stt is None:
        _dictation_instance.set_stt(stt_engine)
    return _dictation_instance
