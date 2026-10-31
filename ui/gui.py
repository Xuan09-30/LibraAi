import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

log_dir = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(log_dir, exist_ok=True)
_runtime_log = open(os.path.join(log_dir, "libra_runtime.log"), "a", encoding="utf-8", buffering=1)

class StreamTee:
    def __init__(self, primary, file_stream):
        self.primary = primary
        self.file_stream = file_stream
    def write(self, data):
        try:
            if self.primary:
                self.primary.write(data)
                self.primary.flush()
        except Exception:
            pass
        try:
            self.file_stream.write(data)
            self.file_stream.flush()
        except Exception:
            pass
    def flush(self):
        try:
            if self.primary:
                self.primary.flush()
        except Exception:
            pass
        try:
            self.file_stream.flush()
        except Exception:
            pass

sys.stdout = StreamTee(sys.stdout, _runtime_log)
sys.stderr = StreamTee(sys.stderr, _runtime_log)

import time

def _handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    import traceback
    err_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"\n[CRITICAL UNCAUGHT EXCEPTION {time.strftime('%Y-%m-%d %H:%M:%S')}]:\n{err_text}", file=sys.stderr)
    try:
        _runtime_log.flush()
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = _handle_uncaught_exception

# GPU Angle / D3D11 Context Reset Resilience for QtWebEngine / WebGL Orb
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--disable-gpu-watchdog "
    "--enable-webgl "
    "--ignore-gpu-blocklist "
    "--enable-gpu-rasterization "
    "--disable-direct-composition "
    "--use-angle=d3d11"
)

# =====================================================================
# ATOMIC WINDOWS SINGLE-INSTANCE GUARD (ZERO IMPORT LATENCY)
# =====================================================================
import ctypes
from ctypes import wintypes

_is_reload = any(arg.startswith("--reload-") or arg.startswith("--reloaded-") for arg in sys.argv) or "pytest" in sys.modules or os.environ.get("LIBRA_TEST_MODE") == "1"
_libra_mutex_handle = None

if not _is_reload:
    ERROR_ALREADY_EXISTS = 183
    MUTEX_NAME = "Local\\ProjectLibra_MasterInstance_Mutex_chenx"

    _kernel32 = ctypes.windll.kernel32
    _kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.CreateMutexW.restype = wintypes.HANDLE

    _libra_mutex_handle = _kernel32.CreateMutexW(None, True, MUTEX_NAME)
    _last_err = _kernel32.GetLastError()

    if _last_err == ERROR_ALREADY_EXISTS or _libra_mutex_handle == 0:
        # A primary instance is already initializing or active!
        print(f"[{time.strftime('%H:%M:%S')}] [SingleInstanceGuard] Duplicate instance detected. Signaling primary instance and terminating immediately.")
        try:
            from PyQt6.QtCore import QCoreApplication
            from PyQt6.QtNetwork import QLocalSocket
            _temp_app = QCoreApplication(sys.argv)
            _sock = QLocalSocket()
            for _ in range(15):
                _sock.connectToServer("libra_instance_ipc")
                if _sock.waitForConnected(500):
                    _sock.write(b"show\n")
                    _sock.waitForBytesWritten(1000)
                    _sock.waitForReadyRead(500)
                    _sock.disconnectFromServer()
                    break
                time.sleep(0.2)
        except Exception:
            pass
        sys.exit(0)
import math
import random
import threading
import warnings
import re
import json
import html
import numpy as np
import pyaudio
import torch
import keyboard
import queue
import wave
import subprocess

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QFrame, QLineEdit, QPushButton, QFileDialog,
    QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QRectF, QUrl
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QBrush, QLinearGradient,
    QAction, QIcon, QPixmap, QPen, QRadialGradient
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

from openwakeword.model import Model
from core.vad import SileroVADDetector
from core.wakeword_booster import WakeWordBooster
from core.kokoro_tts import KokoroTTS
from core.stt import SpeechToText
from core.llm import LocalLLM
from core.orchestrator import SupervisorHub
from core.telemetry import profiler
from core.text_cleaner import normalize_for_tts
from core.audio_capture import scale_pcm_amplitude, get_windows_master_volume, get_dynamic_chime_pcm, AudioDucker
from tools.security_scanner import SecurityScanner
from core.code_reloader import CodeReloader
from core.version import LIBRA_VERSION, get_full_version_string
from ui.spotlight_bar import SpotlightBar
from ui.memory_vault_widget import MemoryVaultWidget
from core.dictation import get_dictation_controller

warnings.filterwarnings("ignore")


class CyberAudioVisualizer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.num_bars = 36
        self.bar_heights = [0.1] * self.num_bars
        self.target_heights = [0.1] * self.num_bars
        self.is_active = False

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._animate_bars)
        self.anim_timer.start(30)

    def set_active(self, active: bool):
        self.is_active = active

    def _animate_bars(self):
        for i in range(self.num_bars):
            if self.is_active:
                center_dist = abs(i - self.num_bars / 2) / (self.num_bars / 2)
                boost = max(0.2, 1.0 - (center_dist * 0.6))
                self.target_heights[i] = random.uniform(0.15, 0.95) * boost
            else:
                self.target_heights[i] = 0.08 + 0.04 * math.sin(time.time() * 3 + i * 0.3)
            self.bar_heights[i] += (self.target_heights[i] - self.bar_heights[i]) * 0.35
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        bar_width = (w - (self.num_bars * 3)) / self.num_bars

        for i in range(self.num_bars):
            x = i * (bar_width + 3)
            bar_h = self.bar_heights[i] * (h - 8)
            y = (h - bar_h) / 2

            gradient = QLinearGradient(x, y, x, y + bar_h)
            if self.is_active:
                gradient.setColorAt(0.0, QColor(56, 189, 248, 255))
                gradient.setColorAt(1.0, QColor(129, 140, 248, 200))
            else:
                gradient.setColorAt(0.0, QColor(148, 163, 184, 80))
                gradient.setColorAt(1.0, QColor(39, 39, 42, 120))

            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(x, y, bar_width, bar_h), 2, 2)


class VoiceAssistantWorker(QThread):
    status_changed = pyqtSignal(str)
    visualizer_state = pyqtSignal(bool)
    mic_level = pyqtSignal(float)
    log_received = pyqtSignal(str, str)
    telemetry_update = pyqtSignal(str, str)
    hud_update_signal = pyqtSignal(str, str)
    orb_state_signal = pyqtSignal(str)
    core_response_signal = pyqtSignal(dict)
    notification_signal = pyqtSignal(str, str)
    game_state_changed = pyqtSignal(bool)
    ui_visibility_signal = pyqtSignal(str)  # 'show', 'hide', 'toggle'

    def __init__(self, raw_chime_pcm: bytes = b""):
        super().__init__()
        self.running = True
        self.interrupted = threading.Event()
        self.input_stream = None  # Holds the PyAudio input handle to clear Pylance closure warning
        self.pa = None
        self.text_input_queue = queue.Queue()
        self.proactive_speech_queue = queue.Queue()
        self.mute_tts = False
        self.llm = None
        self.attached_file_path = None
        self.raw_chime_pcm = raw_chime_pcm
        self.chime_pcm = raw_chime_pcm
        self.audio_ducker = AudioDucker()

    def stop(self):
        self.running = False
        self.interrupted.set()
        try:
            if hasattr(self, "audio_ducker"):
                self.audio_ducker.restore_background_audio()
        except Exception:
            pass
        if self.llm:
            try:
                if hasattr(self.llm, "scheduler") and self.llm.scheduler:
                    self.llm.scheduler.stop_watchdog()
                if hasattr(self.llm, "folder_watchdog") and self.llm.folder_watchdog:
                    self.llm.folder_watchdog.stop()
            except Exception:
                pass
        if hasattr(self, "web_thread") and self.web_thread and hasattr(self.web_thread, "server"):
            try:
                self.web_thread.server.should_exit = True
            except Exception:
                pass

    def submit_text(self, text: str):
        """Allows instant asynchronous submission of typed text commands."""
        self.text_input_queue.put(text)
        self.interrupted.set()

    def run(self):
        print("\n--- [WORKER THREAD INITIALIZING] ---")
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        wakewords_dir = os.path.join(project_root, "assets", "wakewords")
        libra_model = os.path.join(wakewords_dir, "Hey_Libra.onnx")
        stop_model = os.path.join(wakewords_dir, "stop.onnx")

        active_models = []
        if os.path.exists(libra_model):
            active_models.append(libra_model)
        if os.path.exists(stop_model):
            active_models.append(stop_model)

        oww_model = Model(wakeword_models=active_models)
        self.telemetry_update.emit("WAKEWORD", "HEY LIBRA + STOP [BARGE-IN ONLINE]")

        tts = KokoroTTS(voice="af_heart", device="cuda")
        self.telemetry_update.emit("TTS_ENGINE", "KOKORO-82M [CUDA]")

        stt = SpeechToText()
        self.telemetry_update.emit("STT_ENGINE", f"WHISPER [{stt.device.upper()}]")

        # Guarantee Ollama daemon is active before initializing LocalLLM
        try:
            import httpx
            _ollama_ok = False
            try:
                _ollama_ok = (httpx.get("http://localhost:11434/api/tags", timeout=1.5).status_code == 200)
            except Exception:
                pass
            if not _ollama_ok:
                _local_app = os.environ.get("LOCALAPPDATA", "")
                _ollama_exe = os.path.join(_local_app, "Programs", "Ollama", "ollama.exe")
                if os.path.exists(_ollama_exe):
                    import subprocess
                    _cflags = 0x08000000 | 0x00000008  # CREATE_NO_WINDOW | DETACHED_PROCESS
                    subprocess.Popen([_ollama_exe, "serve"], creationflags=_cflags, close_fds=True)
                    print("[Ollama] Auto-launched Ollama daemon into background.")
                    for _ in range(10):
                        time.sleep(0.5)
                        try:
                            if httpx.get("http://localhost:11434/api/tags", timeout=1.0).status_code == 200:
                                print("[Ollama] Daemon online verified.")
                                break
                        except Exception:
                            pass
        except Exception as _o_err:
            print(f"[Ollama Auto-Start Notice]: {_o_err}")

        llm = LocalLLM()
        if self.attached_file_path:
            llm.attached_file_path = self.attached_file_path
        self.llm = llm
        supervisor = SupervisorHub(llm=llm)
        self.telemetry_update.emit("LLM_CORE", "QWEN3-INSTRUCT [SUPERVISOR]")

        # Attach hardware engines to llm so remote web agent can access GPU Whisper and Kokoro
        llm.tts = tts
        llm.stt = stt
        self.stt = stt
        try:
            from core.dictation import get_dictation_controller
            get_dictation_controller(stt_engine=stt)
        except Exception:
            pass

        # Launch Remote Web Agent & Mobile PWA server in daemon thread (Phase 10)
        try:
            from web.server import start_web_server_thread
            self.web_thread = start_web_server_thread(hub=supervisor)
            ts_info = getattr(self.web_thread, "tailscale_info", {})
            pwa_label = ts_info.get("magicdns_domain") or "100.126.60.93:8765"
            self.telemetry_update.emit("WEB_AGENT", f"ONLINE [{pwa_label}]")
        except Exception as web_err:
            print(f"[Web Agent Startup Warning]: {web_err}")

        vad_detector = SileroVADDetector(sample_rate=16000, silence_cutoff_sec=0.8)
        self.telemetry_update.emit("VAD_DETECTOR", "SILERO ONNX [0.8s CUTOFF]")

        # 1. Initialize persistent PyAudio input stream with retry for Windows audio boot
        self.pa = None
        self.input_stream = None
        for attempt in range(5):
            try:
                self.pa = pyaudio.PyAudio()
                self.input_stream = self.pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    frames_per_buffer=512
                )
                self.telemetry_update.emit("AUDIO_STATUS", "MICROPHONE ACTIVE")
                break
            except Exception as audio_err:
                print(f"[Audio Device Wait] Attempt {attempt+1}/5 waiting for audio device: {audio_err}")
                if self.pa:
                    try:
                        self.pa.terminate()
                    except Exception:
                        pass
                    self.pa = None
                time.sleep(1.5)
        if not self.input_stream:
            print("[Audio Notice]: No default microphone input device ready. Falling back to Text/GUI mode.")
            self.telemetry_update.emit("AUDIO_STATUS", "NO MIC DETECTED [TEXT MODE ACTIVE]")
            self.log_received.emit("SYSTEM", "Notice: No microphone input device detected. Libra is running in Text Mode in the background. Plug in a microphone anytime to enable wake word.")

        if not self.raw_chime_pcm:
            chime_path = os.path.join(project_root, "assets", "sounds", "chime.wav")
            if os.path.exists(chime_path):
                try:
                    with wave.open(chime_path, "rb") as wf:
                        self.raw_chime_pcm = wf.readframes(wf.getnframes())
                        self.chime_pcm = self.raw_chime_pcm
                except Exception:
                    pass

        def play_chime_async(chime_bytes: bytes):
            if not chime_bytes or self.mute_tts:
                return
            def _stream_worker():
                try:
                    pa_chime = pyaudio.PyAudio()
                    stream = pa_chime.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=24000,
                        output=True
                    )
                    stream.write(chime_bytes)
                    stream.stop_stream()
                    stream.close()
                    pa_chime.terminate()
                except Exception as ex:
                    print(f"[Chime Playback Error]: {ex}")
            threading.Thread(target=_stream_worker, daemon=True).start()

        self.status_changed.emit("SYSTEM READY // AWAITING VOCAL PROMPT")
        if self.raw_chime_pcm:
            scaled = get_dynamic_chime_pcm(self.raw_chime_pcm, base_gain=0.25)
            play_chime_async(scaled)
        self.notification_signal.emit("Project Libra Online", "Neural Core & Ambient Voice online. Say 'Hey Libra' anytime.")

        def speak_interruptible(text_or_stream):
            if self.mute_tts:
                return
            if isinstance(text_or_stream, str):
                sentences = [text_or_stream]
            else:
                sentences = text_or_stream

            self.interrupted.clear()
            self.status_changed.emit("SPEAKING... [CTRL+SPACE TO STOP]")
            self.visualizer_state.emit(True)
            try:
                if hasattr(self, "audio_ducker") and not getattr(self, "is_game_active", False):
                    self.audio_ducker.duck_background_audio(target_level=0.15)
            except Exception:
                pass

            audio_queue = queue.Queue()
            INTERRUPT_HOTKEY = "ctrl+space"
            out_stream_holder = [None]
            synthesis_done = threading.Event()
            playback_finished = threading.Event()

            def trigger_barge_in():
                print(f"\n[Barge-In]: '{INTERRUPT_HOTKEY}' triggered! Cutting speech.")
                self.interrupted.set()
                try:
                    if hasattr(self, "audio_ducker"):
                        self.audio_ducker.restore_background_audio()
                except Exception:
                    pass
                # Flush pending audio queue
                while not audio_queue.empty():
                    try:
                        audio_queue.get_nowait()
                    except queue.Empty:
                        break
                if out_stream_holder[0]:
                    try:
                        out_stream_holder[0].stop_stream()
                    except Exception:
                        pass

            hotkey_handle = None
            try:
                hotkey_handle = keyboard.add_hotkey(INTERRUPT_HOTKEY, trigger_barge_in)
            except Exception:
                pass

            # CONSUMER THREAD: Stays alive until synthesis completes AND queue drains
            def playback_worker():
                pa_out = pyaudio.PyAudio()
                try:
                    out_stream = pa_out.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=24000,
                        output=True,
                        frames_per_buffer=1200
                    )
                    out_stream_holder[0] = out_stream

                    while not self.interrupted.is_set():
                        try:
                            # Short block wait so thread remains responsive to barge-in
                            chunk = audio_queue.get(timeout=0.05)
                        except queue.Empty:
                            if synthesis_done.is_set():
                                break
                            continue

                        if chunk is None or self.interrupted.is_set():
                            break

                        chunk_size = 1200 * 2
                        for i in range(0, len(chunk), chunk_size):
                            if self.interrupted.is_set():
                                break
                            out_stream.write(chunk[i:i + chunk_size])

                    out_stream.stop_stream()
                    out_stream.close()
                except Exception as ex:
                    print(f"[Playback Error]: {ex}")
                finally:
                    pa_out.terminate()
                    playback_finished.set()

            consumer_thread = threading.Thread(target=playback_worker, daemon=True)
            consumer_thread.start()

            # PRODUCER: Synthesizes via Kokoro sentence-by-sentence and pushes into queue
            try:
                for sentence in sentences:
                    if self.interrupted.is_set():
                        break
                    clean_s = normalize_for_tts(sentence)
                    if not clean_s or not clean_s.strip():
                        continue
                    for chunk_bytes in tts.synthesize_stream(clean_s):
                        if self.interrupted.is_set():
                            break
                        if chunk_bytes:
                            audio_queue.put(chunk_bytes)
            except Exception as ex:
                print(f"[Kokoro Synthesis Error]: {ex}")
            finally:
                synthesis_done.set()
                audio_queue.put(None)

            # Flush input stream and reset wakeword detectors so the user's prior "Hey Libra" doesn't linger
            try:
                if self.input_stream:
                    while self.input_stream.get_read_available() > 0:
                        self.input_stream.read(self.input_stream.get_read_available(), exception_on_overflow=False)
            except Exception:
                pass
            oww_model.reset()
            ww_booster.reset()

            playback_start_time = time.time()

            # Wait until playback naturally ends or user interrupts
            while not playback_finished.is_set() and not self.interrupted.is_set():
                if not self.text_input_queue.empty():
                    trigger_barge_in()
                    break

                # 600ms grace period after starting playback: don't false-trigger on startup audio
                if time.time() - playback_start_time < 0.6:
                    try:
                        if self.input_stream and self.input_stream.get_read_available() >= 512:
                            self.input_stream.read(self.input_stream.get_read_available(), exception_on_overflow=False)
                    except Exception:
                        pass
                    time.sleep(0.02)
                    continue

                try:
                    if self.input_stream and self.input_stream.get_read_available() >= 512:
                        chunk_barge = self.input_stream.read(512, exception_on_overflow=False)
                        audio_np = np.frombuffer(chunk_barge, dtype=np.int16).astype(np.float32) / 32768.0
                        rms = float(np.sqrt(np.mean(audio_np ** 2)))
                        if rms < 0.025:
                            time.sleep(0.01)
                            continue

                        frames_barge = ww_booster.process_chunk(chunk_barge, apply_agc=True)
                        for f_barge in frames_barge:
                            preds_barge = oww_model.predict(f_barge)
                            stop_score = 0.0
                            libra_score = 0.0
                            for m_name, score in preds_barge.items():
                                m_lower = str(m_name).lower()
                                if "stop" in m_lower:
                                    stop_score = max(stop_score, score)
                                elif "libra" in m_lower:
                                    libra_score = max(libra_score, score)

                            # Voice barge-in during active TTS playback:
                            # Triggers on explicit "STOP" or "HEY LIBRA" with lowered adaptive threshold
                            if stop_score >= 0.40 or libra_score >= 0.45:
                                trig_label = "STOP command" if stop_score >= 0.40 else "HEY LIBRA wake word"
                                print(f"\n[Voice Barge-In]: Detected {trig_label} during playback! (stop={stop_score:.2f}, libra={libra_score:.2f}, rms={rms:.3f}). Cutting speech.")
                                trigger_barge_in()
                                break
                except Exception:
                    pass
                time.sleep(0.01)

            if hotkey_handle:
                try:
                    keyboard.remove_hotkey(hotkey_handle)
                except Exception:
                    pass

            consumer_thread.join(timeout=0.5)
            self.visualizer_state.emit(False)

            # Flush mic buffer to prevent echo pickup
            try:
                if self.input_stream:
                    while self.input_stream.get_read_available() > 0:
                        self.input_stream.read(self.input_stream.get_read_available(), exception_on_overflow=False)
            except Exception:
                pass

            try:
                if hasattr(self, "audio_ducker"):
                    self.audio_ducker.restore_background_audio()
            except Exception:
                pass

        # Start ReminderEngine background watchdog to announce due reminders
        def on_reminder_due(reminder):
            task = reminder.get("task", "Reminder")
            is_timer = "timer" in str(task).lower()
            title = "Libra Timer Finished" if is_timer else "Libra Reminder"
            if is_timer:
                announcement = f"Hold up, your {task.lower()} went off right now!"
            else:
                announcement = f"Hold up, your reminder to {task} is due now!"
            print(f"\n[Watchdog] Due reminder: {announcement}")
            self.log_received.emit("LIBRA", announcement)
            self.notification_signal.emit(title, announcement)
            self.proactive_speech_queue.put(announcement)

        if hasattr(llm, "scheduler") and llm.scheduler:
            llm.scheduler.start_watchdog(on_reminder_due, check_interval_sec=1.0)

        if hasattr(llm, "missed_reminders") and llm.missed_reminders:
            count = len(llm.missed_reminders)
            missed_summary = f"Notice: You have {count} missed reminder{'s' if count > 1 else ''} from while offline."
            self.log_received.emit("LIBRA", missed_summary)
            speak_interruptible(missed_summary)

        ww_booster = WakeWordBooster(default_threshold=0.58, vad_assisted_threshold=0.46, gaming_threshold=0.78)
        in_followup_mode = False
        followup_turn_count = 0

        while self.running:
            # Drain any proactive background announcements (e.g. timers, alarms)
            while not self.proactive_speech_queue.empty():
                try:
                    ann = self.proactive_speech_queue.get_nowait()
                    self.orb_state_signal.emit("speaking")
                    speak_interruptible(ann)
                    self.orb_state_signal.emit("idle")
                except queue.Empty:
                    break

            user_text = None
            if not self.text_input_queue.empty():
                try:
                    user_text = self.text_input_queue.get_nowait()
                except queue.Empty:
                    user_text = None

            if user_text is None:
                # Context inspection: Check if foreground window is a game or game_mode active
                is_game_active = False
                if hasattr(llm, "vram_governor") and llm.vram_governor and llm.vram_governor.is_gaming_lite_mode():
                    is_game_active = True
                elif hasattr(llm, "window_engine") and llm.window_engine:
                    try:
                        w_info = llm.window_engine.get_active_window_info()
                        is_game_active = (
                            w_info.get("app_category") == "game"
                            or getattr(llm.model_mgr, "game_mode", False)
                        )
                    except Exception:
                        pass
                ww_booster.set_game_mode(is_game_active)

                if is_game_active:
                    # In game context, strictly forbid follow-up listening to prevent eavesdropping
                    ww_booster.reset()
                    in_followup_mode = False
                    followup_turn_count = 0
                elif ww_booster.is_in_followup_window():
                    in_followup_mode = True
                else:
                    in_followup_mode = False
                    followup_turn_count = 0

                if not in_followup_mode:
                    try:
                        if hasattr(self, "audio_ducker"):
                            self.audio_ducker.restore_background_audio()
                    except Exception:
                        pass
                    self.status_changed.emit("STANDBY // LISTENING FOR WAKE WORD")
                    self.visualizer_state.emit(False)
                    oww_model.reset()
                    ww_booster.reset()

                    while self.running and not in_followup_mode:
                        while not self.proactive_speech_queue.empty():
                            try:
                                ann = self.proactive_speech_queue.get_nowait()
                                self.orb_state_signal.emit("speaking")
                                speak_interruptible(ann)
                                self.orb_state_signal.emit("idle")
                            except queue.Empty:
                                break

                        if not self.text_input_queue.empty():
                            try:
                                user_text = self.text_input_queue.get_nowait()
                            except queue.Empty:
                                user_text = None
                            if user_text:
                                break

                        # Dynamic 1.0s game detection poll during standby listening
                        now_tick = time.time()
                        if now_tick - getattr(self, "_last_game_check", 0.0) > 1.0:
                            self._last_game_check = now_tick
                            curr_game = False
                            if hasattr(llm, "vram_governor") and llm.vram_governor and llm.vram_governor.is_gaming_lite_mode():
                                curr_game = True
                            elif hasattr(llm, "window_engine") and llm.window_engine:
                                try:
                                    w_info = llm.window_engine.get_active_window_info()
                                    curr_game = (
                                        w_info.get("app_category") == "game"
                                        or getattr(llm.model_mgr, "game_mode", False)
                                    )
                                except Exception:
                                    pass
                            self.is_game_active = curr_game
                            if curr_game != is_game_active:
                                is_game_active = curr_game
                                ww_booster.set_game_mode(is_game_active)
                                self.game_state_changed.emit(is_game_active)
                                if is_game_active:
                                    try:
                                        if hasattr(self, "audio_ducker"):
                                            self.audio_ducker.restore_background_audio()
                                    except Exception:
                                        pass
                                    print("[Gaming Shield] Game window active. Activated high-threshold shield (0.78), restored game volume to 100%, and disabled AGC.")

                        if self.input_stream is None:
                            time.sleep(0.1)
                            now = time.time()
                            if now - getattr(self, "_last_mic_poll", 0.0) > 2.0:
                                self._last_mic_poll = now
                                test_pa = pyaudio.PyAudio()
                                try:
                                    stream = test_pa.open(
                                        format=pyaudio.paInt16,
                                        channels=1,
                                        rate=16000,
                                        input=True,
                                        frames_per_buffer=512
                                    )
                                    self.pa = test_pa
                                    self.input_stream = stream
                                    self.status_changed.emit("SYSTEM READY // AWAITING VOCAL PROMPT")
                                    self.telemetry_update.emit("AUDIO_STATUS", "MICROPHONE ACTIVE")
                                    self.notification_signal.emit("Microphone Connected", "Libra voice listening is now online! Say 'Hey Libra' anytime.")
                                    self.log_received.emit("SYSTEM", "Microphone connected successfully. Voice listening online.")
                                except Exception:
                                    try:
                                        test_pa.terminate()
                                    except Exception:
                                        pass
                            continue

                        try:
                            audio_data = self.input_stream.read(512, exception_on_overflow=False)
                        except Exception as read_err:
                            print(f"[Mic Read Error]: {read_err}")
                            if self.input_stream:
                                try:
                                    self.input_stream.stop_stream()
                                    self.input_stream.close()
                                except Exception:
                                    pass
                            self.input_stream = None
                            self.status_changed.emit("MICROPHONE DISCONNECTED // TEXT MODE")
                            self.telemetry_update.emit("AUDIO_STATUS", "NO MIC DETECTED [TEXT MODE ACTIVE]")
                            self.notification_signal.emit("Microphone Disconnected", "Microphone unplugged or lost. Switched to Text Mode.")
                            self.log_received.emit("SYSTEM", "Microphone disconnected. Waiting for microphone reconnection...")
                            continue

                        # Calculate live microphone RMS amplitude and emit for Three.js WebGL orb
                        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                        rms = float(np.sqrt(np.mean(audio_np ** 2)))
                        self.mic_level.emit(min(1.0, rms * 10.0))

                        # 1280-sample frame alignment & AGC via WakeWordBooster
                        frames_1280 = ww_booster.process_chunk(audio_data, apply_agc=True)

                        triggered = False
                        for frame in frames_1280:
                            prediction = oww_model.predict(frame)
                            vad_prob = getattr(vad_detector, "last_prob", 0.0)

                            for model_name, score in prediction.items():
                                if "libra" in str(model_name).lower():
                                    if ww_booster.is_wakeword_triggered(score, vad_prob=vad_prob, in_game=is_game_active):
                                        thresh = ww_booster.get_threshold(vad_prob=vad_prob, in_game=is_game_active)
                                        mode_tag = " [GAME SHIELD]" if is_game_active else ""
                                        print(f"\n[Worker]{mode_tag} Wake word triggered! Score: {score:.3f} (thresh: {thresh:.2f}, vad: {vad_prob:.2f})")
                                        # In gaming mode, preserve combat audio (no ducking)
                                        if not is_game_active:
                                            try:
                                                if hasattr(self, "audio_ducker"):
                                                    self.audio_ducker.duck_background_audio(target_level=0.15)
                                            except Exception:
                                                pass
                                        # Auditory Acknowledgment: Subtle chime in gaming mode
                                        if self.raw_chime_pcm:
                                            chime_gain = 0.15 if is_game_active else 0.35
                                            scaled_chime = get_dynamic_chime_pcm(self.raw_chime_pcm, base_gain=chime_gain)
                                            play_chime_async(scaled_chime)
                                        triggered = True
                                        followup_turn_count = 0
                                        break
                            if triggered:
                                break

                        if triggered:
                            break

                if not self.running:
                    break

                if user_text is None:
                    if in_followup_mode:
                        self.status_changed.emit("CONVERSATIONAL FOLLOW-UP ACTIVE...")
                    else:
                        self.status_changed.emit("RECORDING USER INPUT...")

                    vad_detector.reset()

                    # Pre-populate with pre-roll buffer (1.0s preserved from WakeWordBooster ring buffer)
                    preroll_audio = ww_booster.get_preroll_audio()
                    if len(preroll_audio) > 0:
                        vad_detector.audio_buffer.append(preroll_audio)
                        ww_booster.clear_preroll()

                    followup_wait_timeout = 10.0 if in_followup_mode else 15.0
                    max_recording_time = 25.0
                    listen_start_time = time.time()
                    speech_start_time = None
                    full_audio = None

                    while self.running:
                        if not self.proactive_speech_queue.empty() and not vad_detector.has_spoken:
                            try:
                                ann = self.proactive_speech_queue.get_nowait()
                                self.orb_state_signal.emit("speaking")
                                speak_interruptible(ann)
                                self.orb_state_signal.emit("idle")
                            except queue.Empty:
                                pass

                        if not self.text_input_queue.empty():
                            try:
                                user_text = self.text_input_queue.get_nowait()
                            except queue.Empty:
                                user_text = None
                            if user_text:
                                break

                        now = time.time()

                        if not vad_detector.has_spoken and (now - listen_start_time) > followup_wait_timeout:
                            print("[VAD] Timeout waiting for speech.")
                            ww_booster.clear_followup_window()
                            in_followup_mode = False
                            break

                        if vad_detector.has_spoken and speech_start_time and (now - speech_start_time) > max_recording_time:
                            print("[VAD] Max recording duration reached.")
                            if vad_detector.audio_buffer:
                                full_audio = np.concatenate(vad_detector.audio_buffer, axis=0)
                            break

                        chunk = self.input_stream.read(512, exception_on_overflow=False)
                        chunk_np = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0

                        # Live microphone RMS amplitude for Three.js WebGL orb
                        rms = float(np.sqrt(np.mean(chunk_np ** 2)))
                        self.mic_level.emit(min(1.0, rms * 10.0))

                        is_complete, audio_out = vad_detector.process_chunk(chunk)
                        if vad_detector.has_spoken and speech_start_time is None:
                            speech_start_time = now

                        if is_complete and audio_out is not None:
                            full_audio = audio_out
                            print(f"[VAD] Speech boundary triggered (duration: {len(full_audio)/16000:.2f}s).")
                            break

                    if user_text is None:
                        if full_audio is None or len(full_audio) < 16000 * 0.3:
                            in_followup_mode = False
                            self.status_changed.emit("STANDBY // LISTENING FOR WAKE WORD")
                            continue

                        self.status_changed.emit("NEURAL TRANSCRIBING...")
                        try:
                            with profiler.measure("STT_LATENCY"):
                                user_text = stt.transcribe(full_audio)
                            stt_latency = profiler.current_turn.get("STT_LATENCY", 0.0)
                            self.telemetry_update.emit("STT_LATENCY", f"{stt_latency:.0f} ms")
                        except Exception as stt_err:
                            print(f"[STT Worker Guard]: {stt_err}")
                            self.log_received.emit("ERROR", f"Speech-to-Text Transcription Error: {stt_err}")
                            user_text = None

            if not user_text or not user_text.strip():
                ww_booster.clear_followup_window()
                in_followup_mode = False
                self.status_changed.emit("STANDBY // LISTENING FOR WAKE WORD")
                continue

            # Gaming Shield Post-STT Verification:
            # When gaming, verify that the transcription actually addressed "Libra"
            # to filter out ambient teammate/Discord callouts or conversational chatter.
            if is_game_active and not in_followup_mode:
                text_lower = user_text.lower()
                has_wake_address = bool(re.search(r"\b(?:hey\s+)?libra\b", text_lower)) or "libra" in text_lower
                if not has_wake_address:
                    print(f"[Gaming Shield] Discarded ambient in-game chatter: '{user_text}'. (Wake word 'Libra' not verified)")
                    self.log_received.emit("SYSTEM", f"Gaming Shield: Suppressed in-game chatter '{user_text}'.")
                    ww_booster.clear_followup_window()
                    in_followup_mode = False
                    self.status_changed.emit("STANDBY // LISTENING FOR WAKE WORD")
                    continue

            print(f"[Captured Input]: {user_text}")
            self.log_received.emit("USER", user_text)

            # Check if user spoke solely the wake word ("Hey Libra", "Libra")
            clean_phrase = re.sub(r"[^a-zA-Z]", " ", user_text).strip().lower()
            if clean_phrase in ["hey libra", "libra", "hey", "hello libra"]:
                print(f"[Worker] Standalone wake transcription: '{user_text}'. Playing cybernetic chime.")
                if self.raw_chime_pcm:
                    scaled = get_dynamic_chime_pcm(self.raw_chime_pcm, base_gain=0.35)
                    play_chime_async(scaled)
                ww_booster.set_followup_window(6.0)
                in_followup_mode = True
                followup_turn_count = 0
                continue

            # Direct Voice Window Commands (e.g. "show yourself", "come out", "hide yourself")
            clean_cmd = re.sub(r"[^a-zA-Z\s]", " ", user_text).strip().lower()
            clean_cmd_stripped = re.sub(r"^(?:hey\s+libra|libra|please)\s+", "", clean_cmd).strip().lower()

            SHOW_PHRASES = {
                "show yourself", "show interface", "open interface", "come out",
                "open window", "show window", "open the window", "show the window",
                "open up", "show ui", "open ui", "bring up the window",
                "open libra", "show libra", "show desktop", "come back", "maximize"
            }
            HIDE_PHRASES = {
                "hide yourself", "hide interface", "close interface", "hide window",
                "hide ui", "close window", "close ui", "minimize", "go away",
                "go to background", "hide in background", "disappear", "hide libra"
            }

            if clean_cmd_stripped in SHOW_PHRASES or clean_cmd in SHOW_PHRASES:
                print(f"[Worker] Voice UI Command triggered: SHOW ({user_text})")
                self.ui_visibility_signal.emit("show")
                voice_msg = "Right here, Chen Xuan. Bringing up my interface now."
                self.log_received.emit("LIBRA", voice_msg)
                if not self.mute_tts:
                    self.orb_state_signal.emit("speaking")
                    speak_interruptible(voice_msg)
                self.orb_state_signal.emit("idle")
                ww_booster.clear_followup_window()
                in_followup_mode = False
                self.status_changed.emit("STANDBY // READY")
                continue

            if clean_cmd_stripped in HIDE_PHRASES or clean_cmd in HIDE_PHRASES:
                print(f"[Worker] Voice UI Command triggered: HIDE ({user_text})")
                self.ui_visibility_signal.emit("hide")
                voice_msg = "Minimizing to background. I'll still be listening whenever you call."
                self.log_received.emit("LIBRA", voice_msg)
                if not self.mute_tts:
                    self.orb_state_signal.emit("speaking")
                    speak_interruptible(voice_msg)
                self.orb_state_signal.emit("idle")
                ww_booster.clear_followup_window()
                in_followup_mode = False
                self.status_changed.emit("STANDBY // READY")
                continue

            # STATE 4: REASON & EXECUTE VIA LLM CORE
            self.status_changed.emit("PROCESSING REASONING...")
            self.orb_state_signal.emit("reasoning")
            if hasattr(llm, "idle_daemon") and llm.idle_daemon:
                llm.idle_daemon.record_user_activity()

            try:
                with profiler.measure("LLM_LATENCY"):
                    response_data = supervisor.execute(user_text)
                llm_latency = profiler.current_turn.get("LLM_LATENCY", 0.0)
                self.telemetry_update.emit("LLM_LATENCY", f"{llm_latency:.0f} ms")
                route_label = response_data.get("action") or ("compound" if response_data.get("compound") else "chat")
                profiler.flush(transcript=user_text, route=route_label)
            except Exception as exec_err:
                err_detail = f"{type(exec_err).__name__}: {exec_err}"
                print(f"[Supervisor Worker Guard]: {err_detail}")
                response_data = {
                    "action": "error_recovery",
                    "error": f"Execution Exception ({err_detail})",
                    "voice_response": "I encountered an error while processing that request, but my systems remain online."
                }
            print(f"[Libra Core]: {response_data}")
            self.core_response_signal.emit(response_data)

            # Surface any internal tool or execution error messages in the chatbox terminal
            err_code = response_data.get("error_code") or response_data.get("code")
            err_msg = response_data.get("error") or response_data.get("error_message")
            if err_msg or err_code:
                prefix = f"Error [{err_code}]: " if err_code else "Error: "
                self.log_received.emit("ERROR", f"{prefix}{err_msg}")
            elif response_data.get("status") in ["error", "failed"] and response_data.get("issues"):
                issues_str = "; ".join(str(i) for i in response_data["issues"])
                self.log_received.emit("ERROR", f"Execution Failed: {issues_str}")

            if response_data.get("compound") and response_data.get("step_results"):
                for s_res in response_data["step_results"]:
                    s_err = s_res.get("error") or s_res.get("error_message")
                    s_code = s_res.get("error_code") or s_res.get("code")
                    if s_err or s_code:
                        prefix = f"Step Error [{s_code}]: " if s_code else "Step Error: "
                        self.log_received.emit("ERROR", f"{prefix}{s_err}")

            # Emit HUD card and Orb state updates if present
            try:
                if response_data.get("action") == "data_science" or response_data.get("hud_card"):
                    self.orb_state_signal.emit("data_science")
                    hud_card = response_data.get("hud_card")
                    if hud_card:
                        self.hud_update_signal.emit(
                            hud_card.get("type", "plot"),
                            json.dumps(hud_card)
                        )
                if response_data.get("scratchpad"):
                    self.hud_update_signal.emit("scratchpad", json.dumps(response_data["scratchpad"]))
                if response_data.get("artifacts"):
                    for art in response_data["artifacts"]:
                        self.hud_update_signal.emit("artifact", json.dumps(art))
            except Exception as hud_err:
                print(f"[HUD Emit Guard]: {hud_err}")

            # Grab final voice response formulated and executed by LocalLLM
            voice_msg = response_data.get("voice_response", "Understood.")

            # Emit live desktop step-by-step thought process and Computer-Use action trace
            agent_trace = response_data.get("agent_trace") or []
            t_steps = response_data.get("thought_steps") or []
            if agent_trace:
                for trace_item in agent_trace:
                    self.log_received.emit("STEP", json.dumps(trace_item))
            elif t_steps:
                for s_item in t_steps:
                    self.log_received.emit("THOUGHT_STEP", json.dumps(s_item))

            self.log_received.emit("LIBRA", voice_msg)
            if not self.mute_tts:
                try:
                    self.orb_state_signal.emit("speaking")
                    speak_interruptible(voice_msg)
                except Exception as tts_err:
                    print(f"[TTS Worker Guard]: {tts_err}")
                    self.log_received.emit("ERROR", f"Text-to-Speech Error: {tts_err}")
            self.orb_state_signal.emit("idle")

            # Check if active window is a game or in game_mode
            is_game_active = False
            if hasattr(llm, "vram_governor") and llm.vram_governor and llm.vram_governor.is_gaming_lite_mode():
                is_game_active = True
            elif hasattr(llm, "window_engine") and llm.window_engine:
                try:
                    w_info = llm.window_engine.get_active_window_info()
                    is_game_active = (
                        w_info.get("app_category") == "game"
                        or getattr(llm.model_mgr, "game_mode", False)
                    )
                except Exception:
                    pass
            ww_booster.set_game_mode(is_game_active)

            if is_game_active:
                # Strictly suppress follow-up listening in games to protect gamer voice chat / Discord
                in_followup_mode = False
                ww_booster.reset()
                followup_turn_count = 0
            else:
                u_text_low = (user_text or "").lower().strip()
                v_msg_low = (voice_msg or "").lower().strip()

                is_terminal_politeness = any(
                    phrase in u_text_low
                    for phrase in [
                        "thank you", "thanks", "thank u", "bye", "goodbye", "good bye",
                        "good night", "see you", "that's all", "thats all", "that will be all",
                        "never mind", "nevermind", "cancel", "dismiss", "stop listening", "go to sleep"
                    ]
                ) or any(
                    v_msg_low.startswith(p)
                    for p in ["you're welcome", "anytime", "goodbye", "have a great", "good night"]
                )

                is_oneshot_action = response_data.get("action") in [
                    "close_app", "schedule_timer", "system_control", "media_control"
                ]

                is_question = (
                    voice_msg.strip().endswith("?")
                    or response_data.get("status") == "clarification_needed"
                    or getattr(llm, "pending_chrome_profile", None) is not None
                    or getattr(llm, "pending_clarification", None) is not None
                )

                if is_terminal_politeness or is_oneshot_action:
                    in_followup_mode = False
                    ww_booster.reset()
                    followup_turn_count = 0
                elif is_question:
                    ww_booster.set_followup_window(5.0)
                    in_followup_mode = True
                    followup_turn_count += 1
                elif followup_turn_count == 0 and response_data.get("action") in ["chat", "analyze_screen", "web_research"]:
                    ww_booster.set_followup_window(3.5)
                    in_followup_mode = True
                    followup_turn_count = 1
                else:
                    in_followup_mode = False
                    ww_booster.reset()
                    followup_turn_count = 0

        if self.input_stream:
            try:
                self.input_stream.stop_stream()
                self.input_stream.close()
            except Exception:
                pass
        if getattr(self, "pa", None):
            try:
                self.pa.terminate()
            except Exception:
                pass



# -----------------------------------------------------------------------------
# MAIN WINDOW GLOBAL HOTKEY THREAD (ALT + ENTER TOGGLE)
# -----------------------------------------------------------------------------
HOTKEY_ID_MAIN_WINDOW = 9015
VK_RETURN = 0x0D

class MainWindowHotkeyThread(QThread):
    hotkey_triggered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._keyboard_handle = None
        self._last_trigger_time = 0.0

    def _safe_trigger(self):
        now = time.time()
        if now - self._last_trigger_time < 0.35:
            return
        self._last_trigger_time = now
        self.hotkey_triggered.emit()

    def run(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            MOD_ALT = 0x0001
            MOD_NOREPEAT = 0x4000
            VK_RETURN = 0x0D

            # 1. Win32 RegisterHotKey: Alt + Enter
            success = user32.RegisterHotKey(
                None,
                HOTKEY_ID_MAIN_WINDOW,
                MOD_ALT | MOD_NOREPEAT,
                VK_RETURN
            )
            if success:
                print("[GUI] Global hotkey registered: [Alt + Enter] -> Toggle Libra UI.")
            else:
                print("[GUI Info] Alt + Enter hotkey registered via low-level keyboard hook.")

            # 2. Also register via keyboard module for OS-level reliability
            try:
                import keyboard
                self._keyboard_handle = keyboard.add_hotkey("alt+enter", lambda: self._safe_trigger(), suppress=False)
            except Exception:
                pass

            msg = wintypes.MSG()
            while self._running:
                res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if not isinstance(res, int) or res <= 0:
                    break
                if msg.message == 0x0312 and msg.wParam == HOTKEY_ID_MAIN_WINDOW:
                    self._safe_trigger()
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            user32.UnregisterHotKey(None, HOTKEY_ID_MAIN_WINDOW)
        except Exception as e:
            print(f"[MainWindowHotkeyThread Error]: {e}")

    def stop(self):
        self._running = False
        if self._keyboard_handle:
            try:
                import keyboard
                keyboard.remove_hotkey(self._keyboard_handle)
            except Exception:
                pass
            self._keyboard_handle = None
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.PostQuitMessage(0)
            except Exception:
                pass

class FuturisticVoiceAssistantUI(QMainWindow):
    reload_requested = pyqtSignal(str)

    def __init__(self, start_worker: bool = True):
        super().__init__()
        self.security_scanner = SecurityScanner()
        self.attached_file_path = None
        self.worker = None
        self.tray_icon = None
        self.chime_pcm = b""
        self.raw_chime_pcm = b""
        chime_file = os.path.join(PROJECT_ROOT, "assets", "sounds", "chime.wav")
        if os.path.exists(chime_file):
            try:
                with wave.open(chime_file, "rb") as wf:
                    self.raw_chime_pcm = wf.readframes(wf.getnframes())
                    self.chime_pcm = self.raw_chime_pcm
            except Exception:
                pass
        self.setAcceptDrops(True)
        self.code_reloader = None
        self.ipc_server = None
        self.reload_requested.connect(self.restart_application)

        self.reload_count = 0
        self.reloaded_from = ""
        self.reloaded_at = ""
        for arg in sys.argv[1:]:
            if arg.startswith("--reload-count="):
                try:
                    self.reload_count = int(arg.split("=", 1)[1])
                except ValueError:
                    pass
            elif arg.startswith("--reloaded-from="):
                self.reloaded_from = arg.split("=", 1)[1]
            elif arg.startswith("--reloaded-at="):
                self.reloaded_at = arg.split("=", 1)[1]

        if self.reload_count == 0 and start_worker:
            state_file = os.path.join(PROJECT_ROOT, "logs", "reloader_state.json")
            if os.path.exists(state_file):
                try:
                    with open(state_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if time.time() - data.get("timestamp", 0) < 15:
                        self.reload_count = data.get("reload_count", 0)
                        self.reloaded_from = data.get("last_trigger_file", "")
                        self.reloaded_at = data.get("last_reload_time", "")
                except Exception:
                    pass

        self.memory_vault_dialog = None
        self.spotlight_bar = None
        self.dictation_controller = None
        # Dynamically check if a protected game is actually running
        from core.vram_governor import get_vram_governor
        gov = get_vram_governor()
        self.anti_cheat_safe_mode = bool(gov and gov.is_gaming_lite_mode())
        if start_worker:
            try:
                self.spotlight_bar = SpotlightBar(parent=None)
                if self.anti_cheat_safe_mode:
                    self.spotlight_bar.pause_hotkeys()
            except Exception as e:
                print(f"[GUI Warning] SpotlightBar init: {e}")
                self.spotlight_bar = None
            try:
                self.dictation_controller = get_dictation_controller()
                self.dictation_controller.start()
                if self.anti_cheat_safe_mode:
                    self.dictation_controller.pause()
            except Exception as e:
                print(f"[GUI Warning] DictationController init: {e}")
                self.dictation_controller = None
            if self.anti_cheat_safe_mode:
                print("[Anti-Cheat Safe Mode] Game active at startup. Hotkeys paused until game closes.")

        self.init_ui()
        _ = self.winId()
        self.init_tray_icon()
        self.main_hotkey_thread = None
        if start_worker:
            try:
                self.main_hotkey_thread = MainWindowHotkeyThread(self)
                self.main_hotkey_thread.hotkey_triggered.connect(self.toggle_interface)
                self.main_hotkey_thread.start()
            except Exception as hk_err:
                print(f"[Main Hotkey Init Warning]: {hk_err}")
            self.init_code_reloader()
            self.init_worker()

    def init_ui(self):
        self.setWindowTitle("Project Libra")
        self.resize(1180, 780)
        self.setStyleSheet("background-color: #09090b; color: #f8fafc; font-family: 'Segoe UI', -apple-system, sans-serif;")

        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)

        # 1. Header (High-Class Minimalist)
        header = QHBoxLayout()
        header.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title_label = QLabel("✦ Libra")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #ffffff; letter-spacing: -0.3px;")
        sub_label = QLabel(f"Local AI Companion · Architecture v{LIBRA_VERSION}")
        sub_label.setFont(QFont("Segoe UI", 9))
        sub_label.setStyleSheet("color: #71717a;")
        title_box.addWidget(title_label)
        title_box.addWidget(sub_label)
        header.addLayout(title_box)

        header.addStretch()

        self.vault_btn = QPushButton("◈ Memory Vault")
        self.vault_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.vault_btn.setStyleSheet("""
            QPushButton {
                background: #18181b; color: #f4f4f5;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 6px 14px;
            }
            QPushButton:hover { background: #27272a; border-color: rgba(255, 255, 255, 0.16); }
        """)
        self.vault_btn.setToolTip("Inspect and edit Memory Vault (Obsidian Markdown Sync at assets/vault/)")
        self.vault_btn.clicked.connect(self.open_memory_vault)
        header.addWidget(self.vault_btn)

        self.stat_box = QLabel("● Online · RTX 5060 Ti")
        self.stat_box.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.stat_box.setStyleSheet(
            "color: #34d399; background: rgba(52, 211, 153, 0.08); border: 1px solid rgba(52, 211, 153, 0.2); border-radius: 6px; padding: 6px 12px;"
        )
        header.addWidget(self.stat_box)

        self.clock_label = QLabel()
        self.clock_label.setFont(QFont("Segoe UI", 9))
        self.clock_label.setStyleSheet("color: #71717a; margin-left: 6px;")
        header.addWidget(self.clock_label)
        main_layout.addLayout(header)

        # 2. Status Banner
        self.status_banner = QLabel("Ready")
        self.status_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_banner.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        self.status_banner.setStyleSheet("""
            background: #18181b; color: #cbd5e1; border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px; padding: 8px;
        """)
        main_layout.addWidget(self.status_banner)

        # 3. Main Workspace: 3D Orb Core (Left) + Terminal & Telemetry (Right)
        workspace = QHBoxLayout()
        workspace.setSpacing(14)

        orb_container = QFrame()
        orb_container.setStyleSheet("background-color: #121215; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px;")
        orb_layout = QVBoxLayout(orb_container)
        orb_layout.setContentsMargins(6, 6, 6, 6)

        self.orb_view = QWebEngineView()
        self.orb_view.setStyleSheet("background: transparent;")

        orb_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "orb", "index.html"))
        print(f"[GUI] Loading WebGL Core from: {orb_file_path}")
        self.orb_view.setUrl(QUrl.fromLocalFile(orb_file_path))
        orb_layout.addWidget(self.orb_view)

        workspace.addWidget(orb_container, stretch=5)

        right_container = QVBoxLayout()
        right_container.setSpacing(10)

        self.visualizer = CyberAudioVisualizer(self)
        right_container.addWidget(self.visualizer)

        chat_telemetry_row = QHBoxLayout()
        chat_telemetry_row.setSpacing(10)

        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setFont(QFont("Segoe UI", 10))
        self.terminal.setStyleSheet("""
            background-color: #121215; color: #f1f5f9;
            border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px;
            padding: 14px; line-height: 1.6;
        """)
        chat_telemetry_row.addWidget(self.terminal, stretch=7)

        sidebar = QVBoxLayout()
        sidebar.setSpacing(6)
        sidebar_title = QLabel("SYSTEM METRICS")
        sidebar_title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        sidebar_title.setStyleSheet("color: #71717a; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 4px; text-transform: uppercase;")
        sidebar.addWidget(sidebar_title)

        self.telemetry_labels = {}
        for key in ["WAKEWORD", "STT_ENGINE", "STT_LATENCY", "LLM_CORE", "LLM_LATENCY", "TTS_ENGINE", "VAD_DETECTOR", "WEB_AGENT"]:
            k_lbl = QLabel(key.replace("_", " "))
            k_lbl.setFont(QFont("Segoe UI", 7))
            k_lbl.setStyleSheet("color: #71717a;")
            v_lbl = QLabel("--")
            v_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            v_lbl.setStyleSheet("color: #e2e8f0; margin-bottom: 3px;")
            sidebar.addWidget(k_lbl)
            sidebar.addWidget(v_lbl)
            self.telemetry_labels[key] = v_lbl

        sidebar.addStretch()
        space_badge = QLabel("[CTRL + SPACE] INTERRUPT")
        space_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        space_badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        space_badge.setStyleSheet(
            "background: rgba(251, 191, 36, 0.08); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.25); border-radius: 6px; padding: 5px;"
        )
        sidebar.addWidget(space_badge)

        chat_telemetry_row.addLayout(sidebar, stretch=3)
        right_container.addLayout(chat_telemetry_row)

        workspace.addLayout(right_container, stretch=7)
        main_layout.addLayout(workspace)

        # 4. Status/Transcript Subtitle Label
        self.subtitle_label = QLabel("Ready — Awaiting vocal prompt, typed command, or file drop")
        self.subtitle_label.setFont(QFont("Segoe UI", 9))
        self.subtitle_label.setStyleSheet("""
            background-color: #121215; color: #94a3b8;
            border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px;
            padding: 8px 14px;
        """)
        main_layout.addWidget(self.subtitle_label)

        # 5. Bottom Modern Command Bar: [📎 Attach] [ QLineEdit ] [🔊 Mute]
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)

        self.attach_btn = QPushButton("📎 Attach")
        self.attach_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.attach_btn.setToolTip("Attach a local file (.pdf, .docx, .txt, .py) for auto-security scanning and Q&A")
        self.attach_btn.setStyleSheet("""
            QPushButton {
                background-color: #18181b; color: #e2e8f0;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #27272a; border-color: rgba(255, 255, 255, 0.16);
            }
        """)
        self.attach_btn.clicked.connect(self.open_file_dialog)
        bottom_bar.addWidget(self.attach_btn)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Message Libra or drop a file here...")
        self.input_box.setFont(QFont("Segoe UI", 10))
        self.input_box.setStyleSheet("""
            QLineEdit {
                background-color: #18181b; color: #f8fafc;
                border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 8px;
                padding: 8px 14px; selection-background-color: #38bdf8;
                selection-color: #09090b;
            }
            QLineEdit:focus {
                border: 1px solid #38bdf8;
            }
        """)
        self.input_box.returnPressed.connect(self.submit_typed_text)
        bottom_bar.addWidget(self.input_box, stretch=8)

        self.mute_btn = QPushButton("🔊 Audio")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.mute_btn.setToolTip("Toggle silent text-only replies (Mute Kokoro TTS)")
        self.mute_btn.setStyleSheet("""
            QPushButton {
                background-color: #18181b; color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px;
                padding: 8px 14px;
            }
            QPushButton:checked {
                background-color: rgba(248, 113, 113, 0.15); color: #f87171;
                border: 1px solid rgba(248, 113, 113, 0.3);
            }
        """)
        self.mute_btn.toggled.connect(self.toggle_mute)
        bottom_bar.addWidget(self.mute_btn)

        main_layout.addLayout(bottom_bar)

        # 6. Ultra-Compact Footer: Small Version Number & Live Code Reloader Status
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(4, 2, 4, 0)
        footer_layout.setSpacing(10)

        self.version_label = QLabel()
        self.version_label.setFont(QFont("Segoe UI", 8))
        self.version_label.setTextFormat(Qt.TextFormat.RichText)
        self.version_label.setCursor(Qt.CursorShape.PointingHandCursor)
        footer_layout.addWidget(self.version_label)

        footer_layout.addStretch()

        self.reloader_meta_label = QLabel("WATCHDOG ACTIVE")
        self.reloader_meta_label.setFont(QFont("Segoe UI", 8))
        self.reloader_meta_label.setStyleSheet("color: #52525b;")
        self.reloader_meta_label.setToolTip("Live source code observer powered by watchdog. Any saved modifications to .py or .html files validate AST syntax and automatically hot-reload Project Libra.")
        footer_layout.addWidget(self.reloader_meta_label)

        main_layout.addLayout(footer_layout)

        self.update_version_display()

        timer = QTimer(self)
        timer.timeout.connect(self.update_clock)
        timer.start(1000)
        self.update_clock()

    def update_version_display(self, status_override: str = None):
        if not hasattr(self, "version_label") or self.version_label is None:
            return

        full_ver = get_full_version_string(self.reload_count)

        if status_override:
            html_text = (
                f"<span style='color: #64748b; font-weight: bold;'>LIBRA {full_ver}</span> "
                f"<span style='color: #1e293b;'>|</span> "
                f"<span style='color: #f59e0b; font-weight: bold;'>● {html.escape(status_override)}</span>"
            )
            tooltip = f"Project Libra {full_ver}\nStatus: {status_override}"
        elif self.reload_count > 0:
            src = f" from {self.reloaded_from}" if self.reloaded_from else ""
            t_str = f" at {self.reloaded_at}" if self.reloaded_at else ""
            html_text = (
                f"<span style='color: #00ffcc; font-weight: bold;'>LIBRA {full_ver}</span> "
                f"<span style='color: #1e293b;'>|</span> "
                f"<span style='color: #10b981;'>● RELOADED</span> "
                f"<span style='color: #94a3b8;'>[{t_str.strip()}{src}]</span> "
                f"<span style='color: #1e293b;'>|</span> "
                f"<span style='color: #38bdf8;'>HOT-RELOAD: SYNCD</span>"
            )
            tooltip = (
                f"Project Libra {full_ver}\n"
                f"Reload Revision: #{self.reload_count}\n"
                f"Triggered by: {self.reloaded_from or 'source code'}\n"
                f"Reload Time: {self.reloaded_at}\n"
                f"Live Code Reloader: Active"
            )
        else:
            html_text = (
                f"<span style='color: #00ffcc; font-weight: bold;'>LIBRA {full_ver}</span> "
                f"<span style='color: #1e293b;'>|</span> "
                f"<span style='color: #10b981;'>● LIVE RELOAD ACTIVE</span> "
                f"<span style='color: #64748b;'>[READY]</span>"
            )
            tooltip = (
                f"Project Libra {full_ver}\n"
                f"Initial Process Launch\n"
                f"Live Code Reloader: Active"
            )

        self.version_label.setText(html_text)
        self.version_label.setToolTip(tooltip)

    def submit_typed_text(self):
        text = self.input_box.text().strip()
        if not text:
            return
        self.input_box.clear()
        self.subtitle_label.setText(f"USER: {text}")
        if hasattr(self, "worker") and self.worker is not None:
            self.worker.submit_text(text)
        else:
            self.append_log("USER", text)

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Attach Document for Security Scan & Q&A",
            "",
            "Documents & Code (*.pdf *.docx *.txt *.py *.md *.json *.csv *.log);;All Files (*.*)"
        )
        if file_path:
            self.handle_file_ingestion(file_path)

    def toggle_mute(self, checked: bool):
        if hasattr(self, "worker") and self.worker is not None:
            self.worker.mute_tts = checked
        self.mute_btn.setText("🔇 MUTED" if checked else "🔊 AUDIO")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path and os.path.exists(file_path):
                self.handle_file_ingestion(file_path)

    def handle_file_ingestion(self, file_path: str):
        try:
            filename = os.path.basename(file_path)
            self.append_log("SYSTEM", f"Security scanning dropped file: {filename}...")

            scan_res = self.security_scanner.scan_path(file_path, dry_run=False)
            status = scan_res.get("status")

            if status == "clean":
                self.attached_file_path = file_path
                if hasattr(self, "worker") and self.worker is not None:
                    self.worker.attached_file_path = file_path
                    if hasattr(self.worker, "llm") and self.worker.llm is not None:
                        self.worker.llm.attached_file_path = file_path
                sha = scan_res.get("sha256")
                sha_disp = f" (SHA-256: {sha[:10]}...)" if sha else ""
                msg = f"Scanned {filename}{sha_disp} — no threats found. Ready for questions about this file."
                self.append_log("SECURITY", msg)
                self.subtitle_label.setText(f"FILE ATTACHED: {filename}")
            else:
                primary_issue = scan_res.get("issues", ["Threat detected"])[0] if scan_res.get("issues") else "Threat detected"
                warn_msg = f"Security Alert: Ingestion blocked for {filename} ({primary_issue})."
                self.append_log("SECURITY", warn_msg)
                self.subtitle_label.setText(f"SECURITY BLOCKED: {filename}")
        except Exception as ingest_err:
            self.append_log("ERROR", f"File Ingestion Failure: {ingest_err}")

    def update_clock(self):
        self.clock_label.setText(time.strftime("%H:%M:%S // %Y-%m-%d"))

    def update_telemetry(self, key: str, val: str):
        if key in self.telemetry_labels:
            self.telemetry_labels[key].setText(val)
        if "LATENCY" in key:
            self.stat_box.setText(f"INFERENCE: {val} | VRAM: ACTIVE")

    def set_vis_state(self, active: bool):
        self.visualizer.set_active(active)
        js_cmd = f"if (window.setSpeechActive) {{ window.setSpeechActive({str(active).lower()}); }}"
        self.orb_view.page().runJavaScript(js_cmd)

    def on_mic_level(self, level: float):
        js_cmd = f"if (window.setMicAmplitude) {{ window.setMicAmplitude({level:.3f}); }}"
        self.orb_view.page().runJavaScript(js_cmd)

    def update_hud_card(self, card_type: str, payload_json: str):
        safe_type = json.dumps(card_type)
        safe_payload = json.dumps(payload_json)
        js_cmd = f"if (window.updateHUDCard) {{ window.updateHUDCard({safe_type}, {safe_payload}); }}"
        self.orb_view.page().runJavaScript(js_cmd)

    def set_orb_state(self, mode: str):
        safe_mode = json.dumps(mode)
        js_cmd = f"if (window.setOrbState) {{ window.setOrbState({safe_mode}); }}"
        self.orb_view.page().runJavaScript(js_cmd)

    def update_status(self, text: str):
        self.status_banner.setText(text)
        if "SPEAKING" in text:
            self.status_banner.setStyleSheet(
                "background: #160f29; color: #c084fc; border: 1px solid #9333ea; border-radius: 6px; padding: 9px;"
            )
        elif "RECORDING" in text or "FOLLOW-UP" in text:
            self.status_banner.setStyleSheet(
                "background: #092019; color: #34d399; border: 1px solid #059669; border-radius: 6px; padding: 9px;"
            )
        elif "PROCESSING" in text or "TRANSCRIBING" in text:
            self.status_banner.setStyleSheet(
                "background: #231608; color: #fbbf24; border: 1px solid #d97706; border-radius: 6px; padding: 9px;"
            )
        else:
            self.status_banner.setStyleSheet(
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #091322, stop:0.5 #13243d, stop:1 #091322); "
                "color: #00ffcc; border: 1px solid #00e5ff; border-radius: 6px; padding: 9px;"
            )

    def append_log(self, sender: str, msg: str):
        safe_msg = html.escape(str(msg))
        if sender == "LIBRA":
            color = "#00ffcc"
            bg = "#080d19"
            self.subtitle_label.setText(f"LIBRA: {msg[:120]}...")
        elif sender == "USER":
            color = "#38bdf8"
            bg = "#080d19"
            self.subtitle_label.setText(f"USER: {msg}")
        elif sender == "STEP":
            try:
                st = json.loads(msg) if isinstance(msg, str) and msg.startswith("{") else {}
            except Exception:
                st = {}
            step_i = st.get("step", 1)
            action = str(st.get("action", "act")).upper()
            thought = st.get("thought", msg)
            status = st.get("status", "completed")
            badge_color = "#38bdf8" if action == "CLICK" else ("#a855f7" if action == "TYPE" else ("#ec4899" if action == "PRESS" else "#10b981"))
            if status == "corrected":
                badge_color = "#f59e0b"

            html_step = f"""
            <div style='margin-bottom: 6px; padding: 6px 10px; background: #0b1120; border-left: 3px solid {badge_color}; border-radius: 4px;'>
                <span style='color: {badge_color}; font-weight: bold; font-size: 11px;'>[STEP {step_i}: {action}]</span>
                <span style='color: #f1f5f9; font-size: 12px; margin-left: 6px;'>{html.escape(thought)}</span>
            </div>
            """
            self.terminal.append(html_step)
            self.terminal.verticalScrollBar().setValue(self.terminal.verticalScrollBar().maximum())
            self.subtitle_label.setText(f"LIBRA [STEP {step_i}]: {thought[:100]}")
            return
        elif sender == "THOUGHT_STEP":
            try:
                st = json.loads(msg) if isinstance(msg, str) and msg.startswith("{") else {}
            except Exception:
                st = {}
            title = st.get("title", "THOUGHT")
            detail = st.get("detail", msg)
            status = st.get("status", "completed")
            border_c = "#f59e0b" if status == "corrected" else "#a855f7"

            html_thought = f"""
            <div style='margin-bottom: 6px; padding: 6px 10px; background: #0e0a1e; border-left: 3px solid {border_c}; border-radius: 4px;'>
                <span style='color: {border_c}; font-weight: bold; font-size: 11px;'>🧠 {html.escape(title)}</span>
                <span style='color: #e2e8f0; font-size: 12px; margin-left: 6px;'>{html.escape(detail)}</span>
            </div>
            """
            self.terminal.append(html_thought)
            self.terminal.verticalScrollBar().setValue(self.terminal.verticalScrollBar().maximum())
            return
        elif sender == "THOUGHT":
            color = "#a855f7"
            bg = "#0f091d"
        elif sender == "SECURITY":
            color = "#f43f5e"
            bg = "#1f0a10"
            self.subtitle_label.setText(f"SECURITY ALERT: {msg[:120]}")
        elif sender == "ERROR":
            color = "#ef4444"
            bg = "#25080c"
            self.subtitle_label.setText(f"SYSTEM FAULT: {msg[:120]}")
        else:
            color = "#fbbf24"
            bg = "#080d19"

        html_entry = f"""
        <div style='margin-bottom: 8px; padding: 6px 10px; background: {bg}; border-left: 3px solid {color}; border-radius: 4px;'>
            <span style='color: {color}; font-weight: bold;'>[{sender}]:</span> 
            <span style='color: #f8fafc; font-size: 13px;'>{safe_msg}</span>
        </div>
        """
        self.terminal.append(html_entry)
        self.terminal.verticalScrollBar().setValue(self.terminal.verticalScrollBar().maximum())

    def init_worker(self):
        self.worker = VoiceAssistantWorker(raw_chime_pcm=self.raw_chime_pcm)
        self.worker.status_changed.connect(self.update_status)
        self.worker.visualizer_state.connect(self.set_vis_state)
        self.worker.mic_level.connect(self.on_mic_level)
        self.worker.telemetry_update.connect(self.update_telemetry)
        self.worker.log_received.connect(self.append_log)
        self.worker.hud_update_signal.connect(self.update_hud_card)
        self.worker.orb_state_signal.connect(self.set_orb_state)
        self.worker.core_response_signal.connect(self.handle_core_response)
        self.worker.notification_signal.connect(self.show_notification)
        self.worker.game_state_changed.connect(self._on_game_state_changed)
        self.worker.ui_visibility_signal.connect(self._handle_ui_visibility)
        self.worker.start()

    def _handle_ui_visibility(self, action: str):
        if action == "show":
            self.show_interface()
        elif action == "hide":
            self.hide_interface()
        elif action == "toggle":
            self.toggle_interface()

    def _create_default_tray_icon(self) -> QIcon:
        icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.png")
        if os.path.exists(icon_path):
            try:
                icon = QIcon(icon_path)
                if not icon.isNull():
                    return icon
            except Exception:
                pass

        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Outer cyber ring (Neon Cyan)
        pen = QPen(QColor(0, 229, 255, 230))
        pen.setWidth(4)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(4, 4, size - 8, size - 8)

        # Glowing purple/cyan radial gradient core
        grad = QRadialGradient(size / 2, size / 2, size / 2 - 8)
        grad.setColorAt(0.0, QColor(0, 255, 204, 255))
        grad.setColorAt(0.6, QColor(138, 43, 226, 220))
        grad.setColorAt(1.0, QColor(15, 23, 42, 200))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(8, 8, size - 16, size - 16)

        painter.end()

        try:
            os.makedirs(os.path.join(PROJECT_ROOT, "assets"), exist_ok=True)
            pixmap.save(icon_path, "PNG")
        except Exception:
            pass

        return QIcon(pixmap)

    def open_memory_vault(self):
        if self.memory_vault_dialog is None:
            self.memory_vault_dialog = MemoryVaultWidget(parent=self)
        self.memory_vault_dialog.show()
        self.memory_vault_dialog.raise_()
        self.memory_vault_dialog.activateWindow()

    def init_tray_icon(self):
        icon = self._create_default_tray_icon()
        self.setWindowIcon(icon)
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("Libra // Cybernetic Neural Assistant")

        tray_menu = QMenu()
        show_action = QAction("Show Interface", self)
        show_action.triggered.connect(self.show_interface)
        tray_menu.addAction(show_action)

        hide_action = QAction("Hide Interface", self)
        hide_action.triggered.connect(self.hide_interface)
        tray_menu.addAction(hide_action)

        tray_menu.addSeparator()

        quit_action = QAction("Exit Libra", self)
        quit_action.triggered.connect(self._quit_application)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()
        self.tray_icon.setVisible(True)

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_interface()

    def center_on_screen(self):
        try:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                w = self.width() if self.width() > 100 else 1180
                h = self.height() if self.height() > 100 else 780
                x = max(geo.x(), geo.x() + (geo.width() - w) // 2)
                y = max(geo.y(), geo.y() + (geo.height() - h) // 2)
                self.move(x, y)
        except Exception:
            pass

    def show_interface(self):
        # 1. Center on screen if not positioned or offscreen
        self.center_on_screen()
        # 2. Qt level restore & activate
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()

        # 2. Force Windows 11 DWM to present the window front and center
        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            hwnd = int(self.winId())

            # SW_RESTORE = 9
            user32.ShowWindow(hwnd, 9)

            fg_hwnd = user32.GetForegroundWindow()
            cur_thread = kernel32.GetCurrentThreadId()
            fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0

            attached = False
            if fg_thread and fg_thread != cur_thread:
                attached = bool(user32.AttachThreadInput(cur_thread, fg_thread, True))

            try:
                # Anti-Cheat Safe Mode: Never call user32.keybd_event when bringing window to top
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
            finally:
                if attached:
                    user32.AttachThreadInput(cur_thread, fg_thread, False)

            # Z-order pulse: TOPMOST -> NOTOPMOST forces DWM z-order update
            HWND_TOPMOST = -1
            HWND_NOTOPMOST = -2
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        except Exception:
            pass

    def hide_interface(self):
        self.hide()

    def toggle_interface(self):
        if self.isVisible():
            self.hide_interface()
        else:
            self.show_interface()

    def show_notification(self, title: str, message: str):
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def handle_core_response(self, response: dict):
        action = response.get("action")
        actions = response.get("actions", [])
        if action == "show_ui" or "show_ui" in actions:
            self.show_interface()
        elif action == "hide_ui" or "hide_ui" in actions:
            self.hide_interface()

    def init_code_reloader(self):
        try:
            self.code_reloader = CodeReloader(
                PROJECT_ROOT,
                reload_callback=self._on_code_changed,
                debounce_sec=1.5
            )
            self.code_reloader.start()
        except Exception as e:
            print(f"[CodeReloader Init Error]: {e}")

    def _on_code_changed(self, filepath: str):
        filename = os.path.basename(filepath) if filepath else "source code"
        try:
            self.update_version_display(status_override=f"RELOADING ({filename})...")
        except Exception:
            pass
        self.reload_requested.emit(filepath)

    def restart_application(self, trigger_file: str = ""):
        filename = os.path.basename(trigger_file) if trigger_file else "source code"
        print(f"[CodeReloader] Restarting Libra due to changes in: {trigger_file}")

        try:
            self.update_version_display(status_override=f"RESTARTING ({filename})...")
        except Exception:
            pass

        # Silent background reload: no disruptive popup notifications or balloon toasts
        self.append_log("SYSTEM", f"Auto-refreshing Libra in background - Updated code detected in {filename}.")

        was_visible = self.isVisible()

        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(1000)

        if self.code_reloader is not None:
            self.code_reloader.stop()

        if hasattr(self, "ipc_server") and self.ipc_server:
            try:
                self.ipc_server.close()
            except Exception:
                pass
        try:
            from PyQt6.QtNetwork import QLocalServer
            QLocalServer.removeServer("libra_instance_ipc")
        except Exception:
            pass

        global _libra_mutex_handle
        if _libra_mutex_handle:
            try:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(_libra_mutex_handle)
                _libra_mutex_handle = None
            except Exception:
                pass

        if self.tray_icon:
            self.tray_icon.hide()

        new_count = self.reload_count + 1
        t_str = time.strftime("%H:%M:%S")

        state_path = os.path.join(PROJECT_ROOT, "logs", "reloader_state.json")
        try:
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump({
                    "reload_count": new_count,
                    "last_trigger_file": filename,
                    "last_reload_time": t_str,
                    "timestamp": time.time()
                }, f, indent=2)
        except Exception:
            pass

        python_exe = os.path.join(PROJECT_ROOT, "venv", "Scripts", "pythonw.exe")
        if not os.path.isfile(python_exe):
            python_exe = sys.executable
        main_script = os.path.join(PROJECT_ROOT, "ui", "gui.py")
        cmd = [python_exe, main_script]

        for arg in sys.argv[1:]:
            if arg != "--hidden" and not arg.startswith("--reload-") and not arg.startswith("--reloaded-"):
                cmd.append(arg)

        if not was_visible:
            cmd.append("--hidden")

        cmd.extend([
            f"--reload-count={new_count}",
            f"--reloaded-from={filename}",
            f"--reloaded-at={t_str}"
        ])

        CREATE_NEW_PROCESS_GROUP = 0x00000200
        subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NEW_PROCESS_GROUP,
            close_fds=True
        )

        QApplication.quit()
        os._exit(0)

    def _quit_application(self):
        if self.code_reloader is not None:
            self.code_reloader.stop()
        if getattr(self, "spotlight_bar", None) is not None:
            try:
                if hasattr(self.spotlight_bar, "cleanup"):
                    self.spotlight_bar.cleanup()
                elif hasattr(self.spotlight_bar, "hotkey_thread") and self.spotlight_bar.hotkey_thread:
                    self.spotlight_bar.hotkey_thread.stop()
            except Exception:
                pass
        if getattr(self, "dictation_controller", None) is not None:
            try:
                self.dictation_controller.stop()
            except Exception:
                pass
        if self.tray_icon:
            self.tray_icon.hide()
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait()
        QApplication.quit()

    def _on_game_state_changed(self, is_game_active: bool):
        self.anti_cheat_safe_mode = is_game_active
        if is_game_active:
            print("[Anti-Cheat Safe Mode] Game detected. Pausing global hotkeys to ensure 0 anti-cheat hooks.")
            if self.spotlight_bar and hasattr(self.spotlight_bar, "pause_hotkeys"):
                self.spotlight_bar.pause_hotkeys()
            if self.dictation_controller and hasattr(self.dictation_controller, "pause"):
                self.dictation_controller.pause()
        else:
            print("[Anti-Cheat Safe Mode] Game closed. Restoring global hotkeys [Alt+Space], [Ctrl+Shift+L], [Ctrl+Alt+D].")
            if self.spotlight_bar is None:
                try:
                    self.spotlight_bar = SpotlightBar(parent=None)
                except Exception as e:
                    print(f"[SpotlightBar Restore Warning]: {e}")
            elif hasattr(self.spotlight_bar, "resume_hotkeys"):
                self.spotlight_bar.resume_hotkeys()

            if self.dictation_controller is None:
                try:
                    stt_inst = getattr(self.worker, "stt", None) if hasattr(self, "worker") else None
                    self.dictation_controller = get_dictation_controller(stt_engine=stt_inst)
                    self.dictation_controller.start()
                except Exception as e:
                    print(f"[DictationController Restore Warning]: {e}")
            elif hasattr(self.dictation_controller, "resume"):
                self.dictation_controller.resume()

    def closeEvent(self, event):
        if self.tray_icon and self.tray_icon.isVisible():
            event.ignore()
            self.hide_interface()
        else:
            if self.code_reloader is not None:
                self.code_reloader.stop()
            if self.worker is not None:
                self.worker.stop()
                self.worker.wait()
            event.accept()


if __name__ == "__main__":

    from PyQt6.QtNetwork import QLocalServer, QLocalSocket

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 1. Single Instance Check via Qt Local Socket IPC (bypass on reload-restarts)
    is_reload_restart = any(arg.startswith("--reload-count") for arg in sys.argv)
    if not is_reload_restart:
        socket = QLocalSocket()
        socket.connectToServer("libra_instance_ipc")
        if socket.waitForConnected(800):
            socket.write(b"show\n")
            socket.waitForBytesWritten(1000)
            has_reply = socket.waitForReadyRead(1000)
            if has_reply:
                reply = bytes(socket.readAll()).decode("utf-8", errors="ignore")
                if "ok" in reply.lower():
                    print("[GUI] Existing Libra instance found and activated. Showing window.")
                    socket.disconnectFromServer()
                    sys.exit(0)
            print("[GUI Warning] Existing socket unresponsive or zombie. Taking over as primary instance.")
            socket.disconnectFromServer()

    # 2. Setup IPC Server to receive 'show' commands from subsequent launches
    ipc_server = QLocalServer()
    ipc_server.removeServer("libra_instance_ipc")
    ipc_server.listen("libra_instance_ipc")

    window = FuturisticVoiceAssistantUI()
    window.ipc_server = ipc_server

    def handle_incoming_ipc():
        conn = ipc_server.nextPendingConnection()
        if conn:
            raw = bytes(conn.readAll())
            if not raw:
                conn.waitForReadyRead(250)
                raw = bytes(conn.readAll())
            msg = raw.decode("utf-8", errors="ignore").strip().lower()
            if "hide" in msg:
                window.hide_interface()
            elif "toggle" in msg:
                window.toggle_interface()
            else:
                window.show_interface()
            try:
                conn.write(b"ok\n")
                conn.flush()
            except Exception:
                pass

    ipc_server.newConnection.connect(handle_incoming_ipc)

    is_reload_restart = any(arg.startswith("--reload-count") for arg in sys.argv)
    is_hidden_requested = "--hidden" in sys.argv

    if not is_hidden_requested:
        window.center_on_screen()
        window.show_interface()
        # Guarantee window visibility front & center even if Windows 11 desktop is still loading
        QTimer.singleShot(500, window.show_interface)
        QTimer.singleShot(1500, window.show_interface)
        QTimer.singleShot(3500, window.show_interface)
        QTimer.singleShot(6000, lambda: window.show_interface() if not window.isMinimized() else None)
    else:
        _ = window.winId()
    sys.exit(app.exec())