import os
import sys
import time
import math
import struct
import random
import threading
from datetime import datetime
from collections import deque
import numpy as np
import pyaudio

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from openwakeword.model import Model
from core.tts import TextToSpeech
from core.stt import SpeechToText
from core.llm import LocalLLM
from tools.weather import get_weekly_forecast, get_forecast_for_iso_date
from tools.system_actions import launch_any_application, web_search

from PyQt6.QtCore import Qt, QTimer, QUrl, QThread, pyqtSignal, QEvent
from PyQt6.QtGui import QColor, QAction
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QStackedWidget,
    QSystemTrayIcon,
    QMenu,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings


def calculate_rms(audio_bytes):
    count = len(audio_bytes) // 2
    if count == 0:
        return 0
    shorts = struct.unpack(f"{count}h", audio_bytes)
    return math.sqrt(sum(s * s for s in shorts) / count)


class VoiceAssistantWorker(QThread):
    status_changed = pyqtSignal(str)
    show_table_signal = pyqtSignal(list)
    hide_table_signal = pyqtSignal()

    def __init__(self, model_path="assets/wakewords/Hey_Libra.onnx", threshold=0.35):
        super().__init__()
        self.model_path = model_path
        self.threshold = threshold
        self.running = True
        self.interrupted = threading.Event()

    def run(self):
        print("\n--- [WORKER THREAD INITIALIZING] ---")

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        # In VoiceAssistantWorker.run()
        abs_model_path = os.path.join(project_root, "assets", "wakewords", "Hey_Libra.onnx")
        stop_model_path = os.path.join(project_root, "assets", "wakewords", "stop.onnx")
        
        models_to_load = [abs_model_path]
        if os.path.exists(stop_model_path):
            models_to_load.append(stop_model_path)
            print("[Worker] Loaded stop.onnx for dedicated hardware barge-in.")

        oww_model = Model(wakeword_models=models_to_load)

        self.status_changed.emit("INITIALIZING SYSTEM ENGINES...")

        try:
            print("[Worker] Loading OpenWakeWord...")
            oww_model = Model(wakeword_models=[abs_model_path])
            print("[Worker] Initializing Piper TTS...")
            tts = TextToSpeech()
            print("[Worker] Initializing Whisper STT...")
            stt = SpeechToText()
            print("[Worker] Connecting to Local LLM Core...")
            llm = LocalLLM()
        except Exception as e:
            print(f"[Worker FATAL ERROR during initialization]: {e}")
            self.status_changed.emit("INIT ERROR")
            return

        try:
            pa = pyaudio.PyAudio()
            default_input = pa.get_default_input_device_info()
            print(f"[Worker] Audio In: {default_input['name']}")

            input_stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1280
            )
        except Exception as e:
            print(f"[Worker Mic Stream Error]: {e}")
            self.status_changed.emit("MIC STREAM ERROR")
            return

        def speak_interruptible(text: str):
            """Synthesizes and plays audio asynchronously while actively monitoring

            the microphone for hardware-level barge-in ('stop' or wake word).
            """
            if not text or not text.strip():
                return

            self.interrupted.clear()
            sample_rate = getattr(tts.voice.config, "sample_rate", 22050)

            # 1. Synthesize audio buffer using Piper
            audio_buffer = []
            try:
                for chunk in tts.voice.synthesize(text):
                    data = getattr(chunk, "audio_int16_bytes", chunk)
                    if isinstance(data, bytes):
                        audio_buffer.append(data)
            except Exception as ex:
                print(f"[TTS Synthesis Error]: {ex}")
                return

            full_audio = b"".join(audio_buffer)
            if not full_audio:
                return

            playback_finished = threading.Event()

            # 2. Background audio playback thread
            def play_audio():
                try:
                    out_stream = pa.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=sample_rate,
                        output=True,
                    )
                    chunk_size = 2048
                    for i in range(0, len(full_audio), chunk_size):
                        if self.interrupted.is_set():
                            break
                        out_stream.write(full_audio[i : i + chunk_size])
                    out_stream.stop_stream()
                    out_stream.close()
                except Exception as ex:
                    print(f"[Playback Stream Error]: {ex}")
                finally:
                    playback_finished.set()

            playback_start_time = time.time()
            playback_thread = threading.Thread(target=play_audio, daemon=True)
            playback_thread.start()

            # 3. Interruption detection loop (runs on the main worker thread)
            consecutive_wake_hits = 0
            consecutive_stop_hits = 0
            oww_model.reset()

            while not playback_finished.is_set():
                try:
                    # Inside speak_interruptible while not playback_finished.is_set():
                    mic_data = input_stream.read(1280, exception_on_overflow=False)
                    frame = np.frombuffer(mic_data, dtype=np.int16)

                        # Skip initial 0.3s to avoid audio transient pops
                    if (time.time() - playback_start_time) < 0.3:
                            continue

                    rms = calculate_rms(mic_data)
                        # If your voice spikes noticeably above the speaker audio
                    if rms > 1400:
                        norm = frame.astype(np.float32) / 32768.0
                        phrase = stt.transcribe(norm).lower().strip()
                        if any(w in phrase for w in ["stop", "quiet", "shut up", "hold on", "cancel"]):
                            print(f"[Interruption] Spoken stop command detected: '{phrase}'")
                            self.interrupted.set()
                            playback_thread.join()
                            return
                        else:
                            consecutive_stop_hits = 0

                        # Priority 2: Wake Word Interruption (requires higher confidence to beat speaker bleed)
                    elif "heylibra" in model_name_lower or "hey_libra" in model_name_lower:
                        if score >= 0.72:
                            consecutive_wake_hits += 1
                            if consecutive_wake_hits >= 2:
                                print(
                                    f"\n[Barge-In]: Wake word confirmed during speech ({score:.2f}). Cutting audio."
                                )
                                self.interrupted.set()
                                playback_thread.join()
                                return
                        else:
                            consecutive_wake_hits = 0

                except Exception as e:
                    print(f"[Interruption Loop Warning]: {e}")
                time.sleep(0.01)

            playback_thread.join()

            # 4. Flush residual speaker bleed and echo from the microphone buffer
            oww_model.reset()
            try:
                while input_stream.get_read_available() > 0:
                    input_stream.read(
                        input_stream.get_read_available(),
                        exception_on_overflow=False,
                    )
            except Exception:
                pass

        print("[Worker] Engines online. Entering listening cycle.")
        self.status_changed.emit("ONLINE // READY")

        # Rolling ring buffer to prevent clipping leading phonemes
        pre_roll_buffer = deque(maxlen=4)
        in_followup_mode = False

        while self.running:
            # -------------------------------------------------------------
            # STATE 1: PASSIVE DETECTION (Bypassed during follow-up)
            # -------------------------------------------------------------
            if not in_followup_mode:
                try:
                    raw_audio = input_stream.read(1280, exception_on_overflow=False)
                except Exception as e:
                    time.sleep(0.05)
                    continue

                pre_roll_buffer.append(raw_audio)
                audio_frame = np.frombuffer(raw_audio, dtype=np.int16)
                prediction = oww_model.predict(audio_frame)

                wake_detected = False
                for _, score in prediction.items():
                    if score >= self.threshold:
                        print(f"\n[Worker] Wake word triggered! Score: {score:.3f}")
                        wake_detected = True
                        break

                if not wake_detected:
                    continue

                self.status_changed.emit("WAKE DETECTED // LISTENING...")
                wake_phrases = ["I'm listening.", "Online.", "Yes?", "Listening."]
                speak_interruptible(random.choice(wake_phrases))

            # -------------------------------------------------------------
            # STATE 2: RECORD INPUT (VAD + PRE-ROLL)
            # -------------------------------------------------------------
            if in_followup_mode:
                self.status_changed.emit("FOLLOW-UP // LISTENING...")
            else:
                self.status_changed.emit("RECORDING VOCAL INPUT...")

            recorded_chunks = list(pre_roll_buffer) if not in_followup_mode else []
            pre_roll_buffer.clear()

            silence_start = None
            speech_started = False
            # 1.1s allows natural pauses between words without cutting you off
            silence_timeout = 1.15       
            energy_threshold = 520  
            followup_wait_timeout = 4.5 if in_followup_mode else 12.0
            listen_start_time = time.time()

            while self.running and (time.time() - listen_start_time) < followup_wait_timeout:
                chunk = input_stream.read(1280, exception_on_overflow=False)
                recorded_chunks.append(chunk)

                rms = calculate_rms(chunk)
                if rms > energy_threshold:
                    speech_started = True
                    silence_start = None
                elif speech_started:
                    if silence_start is None:
                        silence_start = time.time()
                    elif (time.time() - silence_start) > silence_timeout:
                        break

            if not speech_started or not recorded_chunks:
                if in_followup_mode:
                    print("[Worker] Follow-up window idle. Returning to standby.")
                    in_followup_mode = False
                self.status_changed.emit("ONLINE // READY")
                continue

            # -------------------------------------------------------------
            # STATE 3: TRANSCRIBE
            # -------------------------------------------------------------
            self.status_changed.emit("PROCESSING AUDIO...")
            raw_data = b"".join(recorded_chunks)
            audio_np = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0

            user_query = stt.transcribe(audio_np).lower().strip()
            print(f"[Captured Input]: {user_query}")

            if not user_query or len(user_query) < 2:
                in_followup_mode = False
                self.status_changed.emit("ONLINE // READY")
                continue

            # Dismissal keywords
            if any(w in user_query for w in ["thank you", "thanks", "bye", "goodbye", "never mind", "that's all", "im good"]):
                speak_interruptible("You're welcome. Standing by.")
                in_followup_mode = False
                self.status_changed.emit("ONLINE // READY")
                continue

            # -------------------------------------------------------------
            # STATE 4: REASONING & EXECUTION (QWEN3:8B)
            # -------------------------------------------------------------
            self.status_changed.emit("NEURAL REASONING...")
            decision = llm.plan_and_respond(user_query)
            action = decision.get("action")
            voice_response = decision.get("voice_response")
            print(f"[Libra Core]: {decision}")

            if action in ["live_research", "recommend_music"]:
                self.status_changed.emit("WEB SYNTHESIS...")
                speak_interruptible(voice_response or "Research completed.")
            elif action == "open_app":
                target_app = decision.get("target_app", "")
                self.status_changed.emit(f"LAUNCHING {target_app.upper()}...")
                success, msg = launch_any_application(target_app)
                speak_interruptible(voice_response or msg)
            elif action == "web_search":
                platform = decision.get("platform", "google")
                query = decision.get("search_query", "")
                self.status_changed.emit(f"SEARCHING {platform.upper()}...")
                msg = web_search(query, platform=platform)
                speak_interruptible(voice_response or msg)
            elif action == "remember_fact":
                self.status_changed.emit("MEMORY COMMITTED...")
                speak_interruptible(voice_response or "Recorded.")
            elif action == "get_weekly_weather":
                self.status_changed.emit("QUERYING 7-DAY TELEMETRY...")
                forecast = get_weekly_forecast()
                if forecast:
                    self.show_table_signal.emit(forecast)
                    speak_interruptible("This is the prediction for the next week.")
                else:
                    speak_interruptible("I was unable to retrieve the weekly atmospheric data.")
            elif action == "get_daily_weather":
                target_date = decision.get("target_date")
                self.status_changed.emit("QUERYING DATE TELEMETRY...")
                answer = get_forecast_for_iso_date(target_date)
                speak_interruptible(answer)
            elif action == "unsupported_weather_range":
                self.status_changed.emit("ATMOSPHERIC LIMIT...")
                speak_interruptible(voice_response or "Atmospheric models only predict up to 14 days ahead.")
            else:
                self.status_changed.emit("LIBRA SPEAKING...")
                speak_interruptible(voice_response or "Online and listening.")

            # Flush residual audio buffers to prevent self-echo
            # Flush mic buffer so speaker output is discarded
            oww_model.reset()
            try:
                while input_stream.get_read_available() > 0:
                    input_stream.read(input_stream.get_read_available(), exception_on_overflow=False)
            except Exception:
                pass
            time.sleep(0.3)

            # Only enter follow-up mode if an action was actually executed
            if decision and decision.get("action"):
                in_followup_mode = True
                self.status_changed.emit("FOLLOW-UP // LISTENING...")
            else:
                in_followup_mode = False
                self.status_changed.emit("ONLINE // READY")

        input_stream.stop_stream()
        input_stream.close()
        pa.terminate()

    def stop(self):
        self.running = False
        self.interrupted.set()
        self.wait()


class LibraGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LIBRA // ADVANCED SYSTEM OVERVIEW")
        self.resize(1440, 840)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #030708;
            }
            * {
                color: #00f0ff;
                font-family: 'Consolas', 'Courier New', monospace;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(24)

        # Left HUD Control Panel
        sidebar = QFrame()
        sidebar.setFixedWidth(310)
        sidebar.setStyleSheet("""
            QFrame {
                border: 1px solid rgba(0, 240, 255, 0.25);
                border-top: 2px solid #00f0ff;
                border-bottom: 2px solid #00f0ff;
                background-color: rgba(3, 15, 20, 0.65);
            }
            QPushButton {
                background-color: rgba(0, 240, 255, 0.04);
                border: 1px solid rgba(0, 240, 255, 0.25);
                color: #8be9fd;
                padding: 12px 14px;
                text-align: left;
                font-weight: 600;
                font-size: 11px;
                letter-spacing: 1px;
                margin-bottom: 8px;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 0.16);
                border: 1px solid #00f0ff;
                color: #ffffff;
            }
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 20, 16, 20)

        panel_tag = QLabel("+ CONTROLES_SYSTEME // MENU")
        panel_tag.setStyleSheet("color: #00ffff; font-size: 11px; font-weight: bold; border: none; margin-bottom: 16px;")
        sidebar_layout.addWidget(panel_tag)

        section_ai = QLabel("INTELLIGENCE ARTIFICIELLE")
        section_ai.setStyleSheet("color: rgba(0, 240, 255, 0.45); font-size: 9px; font-weight: bold; border: none; margin-top: 4px; margin-bottom: 6px;")
        sidebar_layout.addWidget(section_ai)

        sidebar_layout.addWidget(QPushButton("● WAKE MONITOR [ACTIVE]"))
        sidebar_layout.addWidget(QPushButton("● ACTIVER LA VISION"))

        section_perf = QLabel("PERFORMANCES & ACCÈS")
        section_perf.setStyleSheet("color: rgba(0, 240, 255, 0.45); font-size: 9px; font-weight: bold; border: none; margin-top: 8px; margin-bottom: 6px;")
        sidebar_layout.addWidget(section_perf)

        sidebar_layout.addWidget(QPushButton("⚡ GPU BOOST (RTX MODE)"))
        btn_weather = QPushButton("🌦 METEO PREDICTIONS")
        sidebar_layout.addWidget(btn_weather)
        sidebar_layout.addWidget(QPushButton("⚙ CONFIGURATION CORE"))

        sidebar_layout.addStretch()

        system_readout = QLabel(
            "SYS.OS: WIN_X64\n"
            "ENGINE: TENSOR_ONNX\n"
            "NET: LOCALHOST_OFFLINE"
        )
        system_readout.setStyleSheet("color: rgba(0, 240, 255, 0.35); font-size: 9px; border: none; line-height: 140%;")
        sidebar_layout.addWidget(system_readout)

        main_layout.addWidget(sidebar)

        # Right Telemetry + Orb/HUD Area
        right_area = QWidget()
        right_layout = QVBoxLayout(right_area)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)

        self.hud_header = QFrame()
        self.hud_header.setFixedHeight(84)
        self.hud_header.setStyleSheet("""
            QFrame {
                border: 1px solid rgba(0, 240, 255, 0.25);
                background-color: rgba(3, 15, 20, 0.55);
            }
        """)
        header_layout = QHBoxLayout(self.hud_header)
        header_layout.setContentsMargins(20, 8, 20, 8)

        left_stat = QLabel("SYS_STABLE\nLATENCY: 12ms")
        left_stat.setStyleSheet("font-size: 9px; color: rgba(0, 240, 255, 0.5); border: none;")
        header_layout.addWidget(left_stat, alignment=Qt.AlignmentFlag.AlignVCenter)

        clock_container = QVBoxLayout()
        clock_subtag = QLabel("+ LOCAL TIME // UTC+8 +")
        clock_subtag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clock_subtag.setStyleSheet("font-size: 9px; color: rgba(0, 240, 255, 0.55); border: none; letter-spacing: 1px;")

        self.clock_label = QLabel("00:00:00")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #00f0ff; border: none; letter-spacing: 3px;")

        self.date_label = QLabel("00/00/0000")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label.setStyleSheet("font-size: 9px; color: rgba(0, 240, 255, 0.65); border: none;")

        clock_container.addWidget(clock_subtag)
        clock_container.addWidget(self.clock_label)
        clock_container.addWidget(self.date_label)
        header_layout.addLayout(clock_container)

        right_stat = QLabel("STATUS: SECURE\nLINK: STANDALONE")
        right_stat.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_stat.setStyleSheet("font-size: 9px; color: rgba(0, 240, 255, 0.5); border: none;")
        header_layout.addWidget(right_stat, alignment=Qt.AlignmentFlag.AlignVCenter)

        right_layout.addWidget(self.hud_header)

        self.center_stack = QStackedWidget()

        self.orb_view = QWebEngineView()
        self.orb_view.setStyleSheet("background: transparent; border: none;")
        self.orb_view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        self.orb_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.orb_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        base_path = os.path.dirname(os.path.abspath(__file__))
        orb_html_path = os.path.join(base_path, "orb", "index.html")
        if os.path.exists(orb_html_path):
            self.orb_view.setUrl(QUrl.fromLocalFile(orb_html_path))
        self.center_stack.addWidget(self.orb_view)

        self.weather_table = QTableWidget(7, 3)
        self.weather_table.setHorizontalHeaderLabels(["DATE", "TEMPERATURE", "CONDITION"])
        self.weather_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.weather_table.verticalHeader().setVisible(False)
        self.weather_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.weather_table.setStyleSheet("""
            QTableWidget {
                background-color: rgba(3, 15, 20, 0.7);
                color: #00f0ff;
                font-size: 14px;
                gridline-color: rgba(0, 240, 255, 0.15);
                border: 1px solid rgba(0, 240, 255, 0.3);
            }
            QHeaderView::section {
                background-color: rgba(0, 40, 50, 0.85);
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                border: 1px solid rgba(0, 240, 255, 0.25);
                padding: 10px;
            }
            QTableWidget::item { padding: 12px; }
        """)
        self.center_stack.addWidget(self.weather_table)
        right_layout.addWidget(self.center_stack, stretch=1)

        self.status_display = QLabel("[ INITIALIZING TELEMETRY... ]")
        self.status_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_display.setStyleSheet("""
            font-size: 11px;
            font-weight: bold;
            color: #00f0ff;
            border: 1px solid rgba(0, 240, 255, 0.3);
            border-left: 3px solid #00f0ff;
            border-right: 3px solid #00f0ff;
            padding: 8px 30px;
            background-color: rgba(3, 15, 20, 0.8);
            letter-spacing: 2px;
        """)
        right_layout.addWidget(self.status_display, alignment=Qt.AlignmentFlag.AlignHCenter)

        main_layout.addWidget(right_area, stretch=1)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_time_display)
        self.clock_timer.start(1000)
        self.update_time_display()

        btn_weather.clicked.connect(self.toggle_weather_demo)

        # System Tray Integration
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
        tray_menu = QMenu()
        show_action = QAction("Open HUD", self)
        show_action.triggered.connect(self.showNormal)
        quit_action = QAction("Shutdown Libra", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(show_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        # Start background worker
        self.worker = VoiceAssistantWorker()
        self.worker.status_changed.connect(self.update_status)
        self.worker.show_table_signal.connect(self.show_weather_table)
        self.worker.hide_table_signal.connect(self.hide_weather_table)
        self.worker.start()

    def update_time_display(self):
        now = datetime.now()
        self.clock_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(now.strftime("%d/%m/%Y"))

    def update_status(self, text):
        self.status_display.setText(f"[ {text.upper()} ]")

    def show_weather_table(self, forecast_data):
        self.weather_table.setRowCount(len(forecast_data))
        for row, entry in enumerate(forecast_data):
            d_item = QTableWidgetItem(entry.get("date", "--"))
            t_item = QTableWidgetItem(entry.get("temp", "--"))
            c_item = QTableWidgetItem(entry.get("condition", "--"))
            for item in (d_item, t_item, c_item):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.weather_table.setItem(row, 0, d_item)
            self.weather_table.setItem(row, 1, t_item)
            self.weather_table.setItem(row, 2, c_item)
        self.center_stack.setCurrentWidget(self.weather_table)
        QTimer.singleShot(12000, self.hide_weather_table)

    def hide_weather_table(self):
        self.center_stack.setCurrentWidget(self.orb_view)

    def toggle_weather_demo(self):
        if self.center_stack.currentWidget() == self.weather_table:
            self.hide_weather_table()
        else:
            self.show_weather_table(get_weekly_forecast())

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                self.hide()
                self.tray_icon.showMessage(
                    "Libra AI",
                    "Running in background. Say 'Hey Libra' anytime.",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
        super().changeEvent(event)

    def closeEvent(self, event):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LibraGUI()
    window.show()
    sys.exit(app.exec())