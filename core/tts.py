import os
import wave
import io
import pyaudio
from piper.voice import PiperVoice

class TextToSpeech:
    def __init__(self, model_rel_path="assets/voices/en_US-amy-medium.onnx"):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.model_path = os.path.join(base_dir, model_rel_path)

        print("Loading Libra's voice model...")
        self.voice = PiperVoice.load(self.model_path)
        self.audio = pyaudio.PyAudio()
        print("TTS ready.")

    def speak(self, text: str):
        if not text:
            return

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            self.voice.synthesize(text, wav_file)

        wav_io.seek(0)
        with wave.open(wav_io, "rb") as wf:
            stream = self.audio.open(
                format=self.audio.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True
            )
            data = wf.readframes(1024)
            while data:
                stream.write(data)
                data = wf.readframes(1024)
            stream.stop_stream()
            stream.close()

    def terminate(self):
        self.audio.terminate()