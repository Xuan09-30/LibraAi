import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# In pythonw.exe, stdout and stderr are None, causing HF Hub/tqdm to crash. Redirect to log file.
if sys.stdout is None or sys.stderr is None:
    log_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    _runtime_log = open(os.path.join(log_dir, "libra_runtime.log"), "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _runtime_log
    if sys.stderr is None:
        sys.stderr = _runtime_log

import time
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
from core.audio_capture import scale_pcm_amplitude, get_windows_master_volume, get_dynamic_chime_pcm
from tools.security_scanner import SecurityScanner

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
                gradient.setColorAt(0.0, QColor(0, 255, 204, 255))
                gradient.setColorAt(1.0, QColor(138, 43, 226, 200))
            else:
                gradient.setColorAt(0.0, QColor(0, 229, 255, 120))
                gradient.setColorAt(1.0, QColor(15, 30, 60, 180))

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

    def __init__(self, raw_chime_pcm: bytes = b""):
        super().__init__()
        self.running = True
        self.interrupted = threading.Event()
        self.input_stream = None  # Holds the PyAudio input handle to clear Pylance closure warning
        self.text_input_queue = queue.Queue()
        self.proactive_speech_queue = queue.Queue()
        self.mute_tts = False
        self.llm = None
        self.attached_file_path = None
        self.raw_chime_pcm = raw_chime_pcm
        self.chime_pcm = raw_chime_pcm

    def stop(self):
        self.running = False
        self.interrupted.set()
        if self.llm:
            try:
                if hasattr(self.llm, "scheduler") and self.llm.scheduler:
                    self.llm.scheduler.stop_watchdog()
                if hasattr(self.llm, "folder_watchdog") and self.llm.folder_watchdog:
                    self.llm.folder_watchdog.stop()
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

        llm = LocalLLM()
        if self.attached_file_path:
            llm.attached_file_path = self.attached_file_path
        self.llm = llm
        supervisor = SupervisorHub(llm=llm)
        self.telemetry_update.emit("LLM_CORE", "QWEN3-INSTRUCT [SUPERVISOR]")

        vad_detector = SileroVADDetector(sample_rate=16000, silence_cutoff_sec=0.8)
        self.telemetry_update.emit("VAD_DETECTOR", "SILERO ONNX [0.8s CUTOFF]")

        # 1. Initialize persistent PyAudio input stream with 512 samples / 32ms frame size
        pa = pyaudio.PyAudio()
        self.input_stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=512
        )

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

            audio_queue = queue.Queue()
            INTERRUPT_HOTKEY = "ctrl+space"
            out_stream_holder = [None]
            synthesis_done = threading.Event()
            playback_finished = threading.Event()

            def trigger_barge_in():
                print(f"\n[Barge-In]: '{INTERRUPT_HOTKEY}' triggered! Cutting speech.")
                self.interrupted.set()
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

                            # Voice barge-in during active TTS playback strictly requires explicit STOP command.
                            # "Hey Libra" is ignored during active speech to prevent assistant audio echo self-interruption.
                            if stop_score >= 0.70:
                                print(f"\n[Voice Barge-In]: Detected STOP command during playback! (stop={stop_score:.2f}, rms={rms:.3f}). Cutting speech.")
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

        ww_booster = WakeWordBooster(default_threshold=0.50, vad_assisted_threshold=0.32)
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
                if hasattr(llm, "window_engine") and llm.window_engine:
                    try:
                        w_info = llm.window_engine.get_active_window_info()
                        is_game_active = (
                            w_info.get("app_category") == "game"
                            or getattr(llm.model_mgr, "game_mode", False)
                        )
                    except Exception:
                        pass

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

                        audio_data = self.input_stream.read(512, exception_on_overflow=False)

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
                                    if ww_booster.is_wakeword_triggered(score, vad_prob=vad_prob):
                                        # In gaming context, require higher confidence score (>=0.68) to filter out gamer callouts
                                        if is_game_active and score < 0.68:
                                            continue
                                        thresh = ww_booster.get_threshold(vad_prob=vad_prob)
                                        print(f"\n[Worker] Wake word triggered! Score: {score:.3f} (thresh: {thresh:.2f}, vad: {vad_prob:.2f})")
                                        # 0ms Auditory Acknowledgment: Push pre-cached chime straight to PyAudio output
                                        if self.raw_chime_pcm:
                                            scaled_chime = get_dynamic_chime_pcm(self.raw_chime_pcm, base_gain=0.35)
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
            if hasattr(llm, "window_engine") and llm.window_engine:
                try:
                    w_info = llm.window_engine.get_active_window_info()
                    is_game_active = (
                        w_info.get("app_category") == "game"
                        or getattr(llm.model_mgr, "game_mode", False)
                    )
                except Exception:
                    pass

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
        pa.terminate()


class FuturisticVoiceAssistantUI(QMainWindow):
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
        self.init_ui()
        _ = self.winId()
        self.init_tray_icon()
        if start_worker:
            self.init_worker()

    def init_ui(self):
        self.setWindowTitle("LIBRA // CYBERNETIC NEURAL INTERFACE")
        self.resize(1180, 780)
        self.setStyleSheet("background-color: #04070f;")

        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 18, 20, 18)
        main_layout.setSpacing(10)

        # 1. Header
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_label = QLabel("LIBRA AI // NEURAL TERMINAL")
        title_label.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #00ffcc; letter-spacing: 3px;")
        sub_label = QLabel("QUANTUM REASONING CORE // ARCHITECTURE V7.0")
        sub_label.setFont(QFont("Consolas", 8))
        sub_label.setStyleSheet("color: #0088aa; letter-spacing: 1.5px;")
        title_box.addWidget(title_label)
        title_box.addWidget(sub_label)
        header.addLayout(title_box)

        header.addStretch()

        self.stat_box = QLabel("INFERENCE: NOMINAL | VRAM: ACTIVE")
        self.stat_box.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.stat_box.setStyleSheet(
            "color: #00e5ff; background: #0c1524; border: 1px solid #142845; border-radius: 4px; padding: 6px 12px;"
        )
        header.addWidget(self.stat_box)

        self.clock_label = QLabel()
        self.clock_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.clock_label.setStyleSheet("color: #64748b; margin-left: 10px;")
        header.addWidget(self.clock_label)
        main_layout.addLayout(header)

        # 2. Status Banner
        self.status_banner = QLabel("SYSTEM INITIALIZING...")
        self.status_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_banner.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self.status_banner.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #091322, stop:0.5 #13243d, stop:1 #091322);
            color: #00ffcc; border: 1px solid #00e5ff; border-radius: 6px;
            padding: 9px; letter-spacing: 2px;
        """)
        main_layout.addWidget(self.status_banner)

        # 3. Main Workspace: 3D Orb Core (Left) + Terminal & Telemetry (Right)
        workspace = QHBoxLayout()
        workspace.setSpacing(14)

        orb_container = QFrame()
        orb_container.setStyleSheet("background-color: #030708; border: 1px solid #142238; border-radius: 8px;")
        orb_layout = QVBoxLayout(orb_container)
        orb_layout.setContentsMargins(4, 4, 4, 4)

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
        self.terminal.setFont(QFont("Consolas", 10))
        self.terminal.setStyleSheet("""
            background-color: #04060c; color: #cbd5e1;
            border: 1px solid #152238; border-radius: 8px;
            padding: 12px; line-height: 1.5;
        """)
        chat_telemetry_row.addWidget(self.terminal, stretch=7)

        sidebar = QVBoxLayout()
        sidebar.setSpacing(6)
        sidebar_title = QLabel("SYSTEM TELEMETRY")
        sidebar_title.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        sidebar_title.setStyleSheet("color: #00ffcc; border-bottom: 1px solid #152238; padding-bottom: 2px;")
        sidebar.addWidget(sidebar_title)

        self.telemetry_labels = {}
        for key in ["WAKEWORD", "STT_ENGINE", "STT_LATENCY", "LLM_CORE", "LLM_LATENCY", "TTS_ENGINE", "VAD_DETECTOR"]:
            k_lbl = QLabel(key.replace("_", " "))
            k_lbl.setFont(QFont("Consolas", 7))
            k_lbl.setStyleSheet("color: #475569;")
            v_lbl = QLabel("--")
            v_lbl.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            v_lbl.setStyleSheet("color: #38bdf8; margin-bottom: 3px;")
            sidebar.addWidget(k_lbl)
            sidebar.addWidget(v_lbl)
            self.telemetry_labels[key] = v_lbl

        sidebar.addStretch()
        space_badge = QLabel("[CTRL + SPACE] INTERRUPT")
        space_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        space_badge.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        space_badge.setStyleSheet(
            "background: #111d2e; color: #f59e0b; border: 1px dashed #d97706; border-radius: 4px; padding: 4px;"
        )
        sidebar.addWidget(space_badge)

        chat_telemetry_row.addLayout(sidebar, stretch=3)
        right_container.addLayout(chat_telemetry_row)

        workspace.addLayout(right_container, stretch=7)
        main_layout.addLayout(workspace)

        # 4. Status/Transcript Subtitle Label
        self.subtitle_label = QLabel("LIBRA // SYSTEM READY — AWAITING VOCAL PROMPT, COMMAND INPUT, OR FILE DROP")
        self.subtitle_label.setFont(QFont("Consolas", 9))
        self.subtitle_label.setStyleSheet("""
            background-color: #070c18; color: #38bdf8;
            border: 1px solid #142845; border-radius: 4px;
            padding: 6px 12px;
        """)
        main_layout.addWidget(self.subtitle_label)

        # 5. Bottom Cyberpunk Command Bar: [📎 FILE] [ QLineEdit ] [🔊 AUDIO]
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)

        self.attach_btn = QPushButton("📎 FILE")
        self.attach_btn.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.attach_btn.setToolTip("Attach a local file (.pdf, .docx, .txt, .py) for auto-security scanning and Q&A")
        self.attach_btn.setStyleSheet("""
            QPushButton {
                background-color: #0c1829; color: #00ffcc;
                border: 1px solid #142a47; border-radius: 5px;
                padding: 8px 14px;
            }
            QPushButton:hover {
                background-color: #12253f; border-color: #00ffcc;
            }
        """)
        self.attach_btn.clicked.connect(self.open_file_dialog)
        bottom_bar.addWidget(self.attach_btn)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Type a command, ask a question, or drop a file here...")
        self.input_box.setFont(QFont("Consolas", 10))
        self.input_box.setStyleSheet("""
            QLineEdit {
                background-color: #050a14; color: #f1f5f9;
                border: 1px solid #15263f; border-radius: 5px;
                padding: 8px 12px; selection-background-color: #00ffcc;
                selection-color: #050a14;
            }
            QLineEdit:focus {
                border: 1px solid #00ffcc;
            }
        """)
        self.input_box.returnPressed.connect(self.submit_typed_text)
        bottom_bar.addWidget(self.input_box, stretch=8)

        self.mute_btn = QPushButton("🔊 AUDIO")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.mute_btn.setToolTip("Toggle silent text-only replies (Mute Kokoro TTS)")
        self.mute_btn.setStyleSheet("""
            QPushButton {
                background-color: #0c1829; color: #38bdf8;
                border: 1px solid #142a47; border-radius: 5px;
                padding: 8px 14px;
            }
            QPushButton:checked {
                background-color: #2a111b; color: #f43f5e;
                border: 1px solid #e11d48;
            }
        """)
        self.mute_btn.toggled.connect(self.toggle_mute)
        bottom_bar.addWidget(self.mute_btn)

        main_layout.addLayout(bottom_bar)

        timer = QTimer(self)
        timer.timeout.connect(self.update_clock)
        timer.start(1000)
        self.update_clock()

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
        self.worker.start()

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

    def show_interface(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

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

    def _quit_application(self):
        if self.tray_icon:
            self.tray_icon.hide()
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait()
        QApplication.quit()

    def closeEvent(self, event):
        if self.tray_icon and self.tray_icon.isVisible():
            event.ignore()
            self.hide_interface()
        else:
            if self.worker is not None:
                self.worker.stop()
                self.worker.wait()
            event.accept()


if __name__ == "__main__":
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 1. Single Instance Check via Qt Local Socket IPC
    socket = QLocalSocket()
    socket.connectToServer("libra_instance_ipc")
    if socket.waitForConnected(400):
        # Another instance is actively running. If started without --hidden, ask existing instance to show its window.
        if "--hidden" not in sys.argv:
            socket.write(b"show\n")
            socket.waitForBytesWritten(1000)
        sys.exit(0)

    # 2. Setup IPC Server to receive 'show' commands from subsequent launches
    ipc_server = QLocalServer()
    ipc_server.removeServer("libra_instance_ipc")
    ipc_server.listen("libra_instance_ipc")

    window = FuturisticVoiceAssistantUI()

    def handle_incoming_ipc():
        conn = ipc_server.nextPendingConnection()
        if conn:
            conn.waitForReadyRead(500)
            msg = bytes(conn.readAll()).decode("utf-8", errors="ignore")
            if "show" in msg:
                window.show_interface()

    ipc_server.newConnection.connect(handle_incoming_ipc)

    if "--hidden" not in sys.argv:
        window.show()
    else:
        _ = window.winId()
    sys.exit(app.exec())