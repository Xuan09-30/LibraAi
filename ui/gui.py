import os
import sys
import time
import math
import random
import threading
import warnings
import numpy as np
import pyaudio
import torch
import keyboard
import queue

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QRectF, QUrl
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QLinearGradient
from PyQt6.QtWebEngineWidgets import QWebEngineView

from openwakeword.model import Model
from silero_vad import load_silero_vad
from core.kokoro_tts import KokoroTTS
from core.stt import SpeechToText
from core.llm import LocalLLM

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

    def __init__(self):
        super().__init__()
        self.running = True
        self.interrupted = threading.Event()
        self.input_stream = None  # Holds the PyAudio input handle to clear Pylance closure warning

    def stop(self):
        self.running = False
        self.interrupted.set()

    def run(self):
        print("\n--- [WORKER THREAD INITIALIZING] ---")
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        wakewords_dir = os.path.join(project_root, "assets", "wakewords")
        libra_model = os.path.join(wakewords_dir, "Hey_Libra.onnx")

        active_models = [libra_model] if os.path.exists(libra_model) else []
        oww_model = Model(wakeword_models=active_models)
        self.telemetry_update.emit("WAKEWORD", "HEY LIBRA [ONLINE]")

        tts = KokoroTTS(voice="af_heart", device="cuda")
        self.telemetry_update.emit("TTS_ENGINE", "KOKORO-82M [CUDA]")

        stt = SpeechToText()
        self.telemetry_update.emit("STT_ENGINE", f"WHISPER [{stt.device.upper()}]")

        llm = LocalLLM()
        self.telemetry_update.emit("LLM_CORE", "QWEN3-INSTRUCT [LOCAL]")

        vad_model = load_silero_vad()
        self.telemetry_update.emit("VAD_DETECTOR", "SILERO V4 [ACTIVE]")

        # 1. Initialize persistent PyAudio input & output streams before defining helpers
        pa = pyaudio.PyAudio()
        self.input_stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1280
        )

        pa_out_master = pyaudio.PyAudio()
        self.status_changed.emit("SYSTEM READY // AWAITING VOCAL PROMPT")

        def speak_interruptible(text: str):
            if not text or not text.strip():
                return

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
                        frames_per_buffer=2400
                    )
                    out_stream_holder[0] = out_stream

                    while not self.interrupted.is_set():
                        try:
                            # Short block wait so thread remains responsive to barge-in
                            chunk = audio_queue.get(timeout=0.1)
                        except queue.Empty:
                            # Only exit if the producer has explicitly finished synthesizing
                            if synthesis_done.is_set():
                                break
                            continue

                        if chunk is None or self.interrupted.is_set():
                            break

                        chunk_size = 2400 * 2
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

            # PRODUCER: Synthesizes via Kokoro and pushes into queue
            try:
                for chunk_bytes in tts.synthesize_stream(text):
                    if self.interrupted.is_set():
                        break
                    if chunk_bytes:
                        audio_queue.put(chunk_bytes)
            except Exception as ex:
                print(f"[Kokoro Synthesis Error]: {ex}")
            finally:
                # Mark producer finished and signal consumer
                synthesis_done.set()
                audio_queue.put(None)

            # Wait until playback naturally ends or user interrupts
            while not playback_finished.is_set() and not self.interrupted.is_set():
                time.sleep(0.01)

            if hotkey_handle:
                try:
                    keyboard.remove_hotkey(hotkey_handle)
                except Exception:
                    pass

            consumer_thread.join(timeout=1.0)
            self.visualizer_state.emit(False)

            # Flush mic buffer to prevent echo pickup
            try:
                if self.input_stream:
                    while self.input_stream.get_read_available() > 0:
                        self.input_stream.read(self.input_stream.get_read_available(), exception_on_overflow=False)
            except Exception:
                pass

        in_followup_mode = False
        pre_roll_buffer = []

        while self.running:
            if not in_followup_mode:
                self.status_changed.emit("STANDBY // LISTENING FOR WAKE WORD")
                self.visualizer_state.emit(False)
                oww_model.reset()

                while self.running and not in_followup_mode:
                    audio_data = self.input_stream.read(1280, exception_on_overflow=False)
                    pre_roll_buffer.append(audio_data)
                    if len(pre_roll_buffer) > 10:
                        pre_roll_buffer.pop(0)

                    audio_frame = np.frombuffer(audio_data, dtype=np.int16)
                    prediction = oww_model.predict(audio_frame)

                    for model_name, score in prediction.items():
                        if "libra" in str(model_name).lower() and score >= 0.50:
                            print(f"\n[Worker] Wake word triggered! Score: {score:.3f}")
                            break
                    else:
                        continue
                    break

            if in_followup_mode:
                self.status_changed.emit("CONVERSATIONAL FOLLOW-UP ACTIVE...")
            else:
                self.status_changed.emit("RECORDING USER INPUT...")

            recorded_chunks = list(pre_roll_buffer) if not in_followup_mode else []
            pre_roll_buffer.clear()

            speech_started = False
            silence_start = None

            # Relaxed timing: 10s wait for next prompt, 25s maximum sentence length
            followup_wait_timeout = 10.0 if in_followup_mode else 15.0
            max_recording_time = 25.0
            listen_start_time = time.time()
            speech_start_time = None

            while self.running:
                now = time.time()

                if not speech_started and (now - listen_start_time) > followup_wait_timeout:
                    break

                if speech_started and (now - speech_start_time) > max_recording_time:
                    break

                chunk = self.input_stream.read(1280, exception_on_overflow=False)
                recorded_chunks.append(chunk)

                audio_np = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0

                # Calculate live microphone RMS amplitude and emit for Three.js orb
                rms = float(np.sqrt(np.mean(audio_np ** 2)))
                self.mic_level.emit(min(1.0, rms * 8.0))

                # Feed 512-sample slice to Silero VAD
                chunk_512 = torch.from_numpy(audio_np[:512])
                with torch.no_grad():
                    speech_prob = vad_model(chunk_512, 16000).item()

                if speech_prob >= 0.50:
                    if not speech_started:
                        speech_started = True
                        speech_start_time = now
                    silence_start = None
                elif speech_started:
                    if silence_start is None:
                        silence_start = now
                    # 2.2 seconds of silence required to end turn
                    elif (now - silence_start) >= 2.2:
                        print(f"[VAD] End of speech detected (Silence: {now - silence_start:.2f}s).")
                        break

            if not speech_started or not recorded_chunks:
                in_followup_mode = False
                self.status_changed.emit("STANDBY // LISTENING FOR WAKE WORD")
                continue

            self.status_changed.emit("NEURAL TRANSCRIBING...")
            t0 = time.time()
            raw_audio = b"".join(recorded_chunks)
            audio_array = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
            user_text = stt.transcribe(audio_array)
            stt_latency = (time.time() - t0) * 1000
            self.telemetry_update.emit("STT_LATENCY", f"{stt_latency:.0f} ms")

            if not user_text.strip():
                in_followup_mode = False
                self.status_changed.emit("STANDBY // LISTENING FOR WAKE WORD")
                continue

            print(f"[Captured Input]: {user_text}")
            self.log_received.emit("USER", user_text)

            # STATE 4: REASON & EXECUTE VIA LLM CORE
            self.status_changed.emit("PROCESSING REASONING...")
            t_llm = time.time()
            response_data = llm.plan_and_respond(user_text)
            llm_latency = (time.time() - t_llm) * 1000
            self.telemetry_update.emit("LLM_LATENCY", f"{llm_latency:.0f} ms")
            print(f"[Libra Core]: {response_data}")

            # Grab final voice response formulated and executed by LocalLLM
            voice_msg = response_data.get("voice_response", "Understood.")

            self.log_received.emit("LIBRA", voice_msg)
            speak_interruptible(voice_msg)
            in_followup_mode = True

        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
        pa.terminate()
        pa_out_master.terminate()


class FuturisticVoiceAssistantUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.init_worker()

    def init_ui(self):
        self.setWindowTitle("LIBRA // CYBERNETIC NEURAL INTERFACE")
        self.resize(1180, 720)
        self.setStyleSheet("background-color: #04070f;")

        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 18, 20, 18)
        main_layout.setSpacing(12)

        # 1. Header
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_label = QLabel("LIBRA AI // NEURAL TERMINAL")
        title_label.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #00ffcc; letter-spacing: 3px;")
        sub_label = QLabel("QUANTUM REASONING CORE // ARCHITECTURE V3.2")
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

        timer = QTimer(self)
        timer.timeout.connect(self.update_clock)
        timer.start(1000)
        self.update_clock()

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
        color = "#00ffcc" if sender == "LIBRA" else "#fbbf24"
        html = f"""
        <div style='margin-bottom: 8px; padding: 5px 8px; background: #080d19; border-left: 3px solid {color}; border-radius: 3px;'>
            <span style='color: {color}; font-weight: bold;'>[{sender}]:</span> 
            <span style='color: #f8fafc; font-size: 13px;'>{msg}</span>
        </div>
        """
        self.terminal.append(html)
        self.terminal.verticalScrollBar().setValue(self.terminal.verticalScrollBar().maximum())

    def init_worker(self):
        self.worker = VoiceAssistantWorker()
        self.worker.status_changed.connect(self.update_status)
        self.worker.visualizer_state.connect(self.set_vis_state)
        self.worker.mic_level.connect(self.on_mic_level)
        self.worker.telemetry_update.connect(self.update_telemetry)
        self.worker.log_received.connect(self.append_log)
        self.worker.start()

    def closeEvent(self, event):
        self.worker.stop()
        self.worker.wait()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FuturisticVoiceAssistantUI()
    window.show()
    sys.exit(app.exec())