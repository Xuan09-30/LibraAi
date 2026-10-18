import os
import sys
import wave
import pytest
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.generate_chime import generate_cybernetic_chime
from core.audio_capture import (
    scale_pcm_amplitude,
    get_windows_master_volume,
    get_dynamic_chime_pcm,
)


class TestCyberneticChime:
    @pytest.fixture(autouse=True)
    def setup_test(self):
        self.chime_path = os.path.join(PROJECT_ROOT, "assets", "sounds", "chime.wav")
        # Ensure chime file exists
        if not os.path.exists(self.chime_path):
            generate_cybernetic_chime(output_path=self.chime_path)

    def test_chime_file_format(self):
        """Validates that chime.wav exists and matches Kokoro 24kHz 16-bit mono PCM."""
        assert os.path.exists(self.chime_path), f"Missing chime file at: {self.chime_path}"

        with wave.open(self.chime_path, "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            duration = nframes / framerate

            assert channels == 1, f"Expected 1 channel (mono), got {channels}"
            assert sampwidth == 2, f"Expected 2 bytes (16-bit), got {sampwidth}"
            assert framerate == 24000, f"Expected 24000 Hz (24kHz), got {framerate}"
            assert 0.05 <= duration <= 0.10, f"Expected ~75ms duration, got {duration*1000:.1f}ms"

    def test_procedural_chime_generation(self, tmp_path):
        """Tests that generate_cybernetic_chime creates a valid custom output."""
        custom_out = str(tmp_path / "custom_chime.wav")
        res = generate_cybernetic_chime(output_path=custom_out, duration=0.075, sr=24000)
        assert os.path.exists(res)

        with wave.open(res, "rb") as wf:
            assert wf.getframerate() == 24000
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2

    def test_scale_pcm_amplitude(self):
        """Tests in-memory 16-bit PCM scaling with volume clamping and zero mutation."""
        # Generate a small 16-bit sine wave test chunk
        samples = (np.sin(np.linspace(0, 2 * np.pi, 240)) * 10000).astype(np.int16)
        raw_pcm = samples.tobytes()

        # Gain 1.0 (identity)
        scaled_1 = scale_pcm_amplitude(raw_pcm, 1.0)
        assert scaled_1 == raw_pcm

        # Gain 0.0 (mute)
        scaled_0 = scale_pcm_amplitude(raw_pcm, 0.0)
        assert scaled_0 == b"\x00" * len(raw_pcm)

        # Gain 0.5 (half amplitude)
        scaled_half = scale_pcm_amplitude(raw_pcm, 0.5)
        half_samples = np.frombuffer(scaled_half, dtype=np.int16)
        np.testing.assert_allclose(half_samples, (samples * 0.5).astype(np.int16), atol=2)

    def test_windows_master_volume_query(self):
        """Tests that get_windows_master_volume returns a float in [0.0, 1.0]."""
        vol = get_windows_master_volume()
        assert isinstance(vol, float)
        assert 0.0 <= vol <= 1.0

    def test_dynamic_chime_pcm_generation(self):
        """Tests adaptive buffer scaling against Windows master volume."""
        with wave.open(self.chime_path, "rb") as wf:
            raw_bytes = wf.readframes(wf.getnframes())

        dynamic_bytes = get_dynamic_chime_pcm(raw_bytes, base_gain=0.35)
        # Should produce valid non-empty byte buffer of same length as original
        assert isinstance(dynamic_bytes, bytes)
        assert len(dynamic_bytes) == len(raw_bytes)

    def test_ui_gui_chime_loading(self):
        """Verifies that FuturisticVoiceAssistantUI loads chime_pcm into memory at startup."""
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt6.QtWidgets import QApplication
        from ui.gui import FuturisticVoiceAssistantUI, VoiceAssistantWorker

        app = QApplication.instance() or QApplication(sys.argv)
        ui = FuturisticVoiceAssistantUI(start_worker=False)

        assert hasattr(ui, "raw_chime_pcm")
        assert hasattr(ui, "chime_pcm")
        assert len(ui.raw_chime_pcm) > 0, "Chime PCM was not loaded into UI memory"
        assert len(ui.chime_pcm) == len(ui.raw_chime_pcm)

        # Verify worker accepts raw_chime_pcm
        worker = VoiceAssistantWorker(raw_chime_pcm=ui.raw_chime_pcm)
        assert worker.raw_chime_pcm == ui.raw_chime_pcm
        assert worker.chime_pcm == ui.chime_pcm

        ui._quit_application()
