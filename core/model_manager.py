import io
import time
import base64
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime

MODEL_PROFILES = {
    "fast_chat": {
        "model": "qwen3:8b",
        "keep_alive": "30m",
        "think": False,
        "vram_estimate_gb": 5.2,
        "description": "Everyday low-latency voice and OS copilot"
    },
    "heavy_research": {
        "model": "qwen3:14b",
        "keep_alive": "2m",
        "think": True,
        "vram_estimate_gb": 9.5,
        "description": "Deep reasoning, architecture, and multi-source research"
    },
    "vision": {
        "model": "qwen2.5vl:7b",
        "keep_alive": "2m",
        "think": False,
        "vram_estimate_gb": 5.0,
        "description": "Local screen visual reasoning and UI inspection"
    },
    "game_mode": {
        "model": "qwen2.5:1.5b",
        "keep_alive": "15m",
        "think": False,
        "vram_estimate_gb": 1.1,
        "description": "Minimal VRAM footprint for active competitive gaming"
    }
}


class ModelManager:
    """
    Dynamic VRAM Swapper & Multi-Model Orchestrator for 16GB VRAM configurations.
    Enforces active eviction (keep_alive: 0) to prevent OOM errors when switching
    between fast_chat (8B), heavy_research (14B), and vision (7B).
    """

    def __init__(self, ollama_host: str = "http://localhost:11434"):
        self.ollama_host = ollama_host.rstrip("/")
        self.current_loaded_model = "qwen3:8b"
        self.game_mode_active = False
        self.eviction_history: List[Dict[str, Any]] = []
        self.available_models = self._fetch_available_models()

    def _fetch_available_models(self) -> List[str]:
        """Queries local Ollama tags to check which models are pulled."""
        try:
            resp = requests.get(f"{self.ollama_host}/api/tags", timeout=2.5)
            if resp.status_code == 200:
                raw_models = resp.json().get("models", [])
                names = []
                for m in raw_models:
                    raw_name = m.get("name", "")
                    names.append(raw_name)
                    # Also add without :latest tag
                    if ":" in raw_name:
                        names.append(raw_name.split(":")[0])
                return list(set(names))
        except Exception as e:
            print(f"[ModelManager Tags Warning]: {e}")
        return ["qwen3:8b", "nomic-embed-text"]

    def is_model_available(self, model_name: str) -> bool:
        """Checks if a given model is available locally in Ollama."""
        if not self.available_models:
            return model_name == "qwen3:8b"
        target_clean = model_name.lower().strip()
        for m in self.available_models:
            m_clean = m.lower().strip()
            if target_clean == m_clean or target_clean == m_clean.split(":")[0]:
                return True
        return False

    def evict_model(self, model_name: str, dry_run: bool = False) -> bool:
        """
        Immediately unloads a model from GPU VRAM by sending keep_alive: 0 to Ollama.
        """
        if not model_name:
            return True

        record = {
            "evicted": model_name,
            "timestamp": datetime.now().isoformat(),
            "dry_run": dry_run
        }
        self.eviction_history.append(record)

        if dry_run:
            return True

        try:
            # POST /api/generate with keep_alive: 0 unloads model immediately
            resp = requests.post(
                f"{self.ollama_host}/api/generate",
                json={"model": model_name, "keep_alive": 0},
                timeout=4.0
            )
            return resp.status_code == 200
        except Exception as e:
            print(f"[ModelManager Eviction Warning]: {e}")
            return False

    def acquire_model(self, profile_key: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Swaps VRAM to the requested model profile.
        If a heavy model is requested and a different model is currently loaded,
        evicts the loaded model first to prevent 16GB VRAM overflow.
        Falls back gracefully to qwen3:8b if the target model is not pulled.
        """
        spec = dict(MODEL_PROFILES.get(profile_key, MODEL_PROFILES["fast_chat"]))
        desired_model = spec["model"]

        # Check if desired model is installed locally
        if not self.is_model_available(desired_model):
            # Graceful fallback to 8B or available chat model
            fallback_model = "qwen3:8b"
            spec["fallback"] = True
            spec["requested_model"] = desired_model
            spec["active_model"] = fallback_model
            target_model = fallback_model
        else:
            spec["fallback"] = False
            spec["requested_model"] = desired_model
            spec["active_model"] = desired_model
            target_model = desired_model

        # Prevent VRAM overflow: Evict prior loaded model when switching models or to heavy/specialized profiles
        should_evict = (
            (self.current_loaded_model and self.current_loaded_model != desired_model)
            or (profile_key in ["heavy_research", "vision", "game_mode"] and self.current_loaded_model)
        )
        if should_evict and self.current_loaded_model:
            self.evict_model(self.current_loaded_model, dry_run=dry_run)

        self.current_loaded_model = target_model
        return spec

    def set_game_mode(self, enabled: bool, dry_run: bool = False) -> Dict[str, Any]:
        """
        Toggles Game Mode:
        When enabled: Evicts heavy models and locks active profile to lightweight 1.5B (or fallback).
        When disabled: Restores 8B fast_chat profile with 30m keep-alive.
        """
        self.game_mode_active = enabled

        if enabled:
            # Free VRAM for the game
            if self.current_loaded_model and self.current_loaded_model in ["qwen3:8b", "qwen3:14b"]:
                self.evict_model(self.current_loaded_model, dry_run=dry_run)

            spec = self.acquire_model("game_mode", dry_run=dry_run)
            return {
                "status": "game_mode_enabled",
                "active_model": spec["active_model"],
                "fallback": spec.get("fallback", False),
                "voice_response": "Game mode activated. VRAM freed for high FPS gaming."
            }
        else:
            # Restore standard copilot
            spec = self.acquire_model("fast_chat", dry_run=dry_run)
            return {
                "status": "game_mode_disabled",
                "active_model": spec["active_model"],
                "voice_response": "Game mode deactivated. Full assistant capabilities restored."
            }

    def analyze_screen(self, prompt: str = "", dry_run: bool = False) -> Dict[str, Any]:
        """
        Captures the primary display and analyzes it using the local vision model profile.
        """
        clean_prompt = prompt or "Describe what you see on the screen concisely in 1-2 spoken sentences."

        if dry_run:
            return {
                "status": "analyzed",
                "vision_response": f"[Dry Run] Screen analyzed for: {clean_prompt}",
                "voice_response": "I see your screen. Everything appears operational."
            }

        vision_spec = self.acquire_model("vision", dry_run=False)
        active_vision_model = vision_spec["active_model"]

        # Capture primary monitor screenshot
        b64_image = None
        try:
            from PIL import ImageGrab
            screenshot = ImageGrab.grab()
            # Downscale if wider than 1280px to preserve inference latency
            if screenshot.width > 1280:
                scale = 1280.0 / screenshot.width
                new_size = (1280, int(screenshot.height * scale))
                screenshot = screenshot.resize(new_size)

            buffer = io.BytesIO()
            screenshot.save(buffer, format="JPEG", quality=85)
            b64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception as e:
            print(f"[ModelManager Screen Capture Warning]: {e}")

        if not b64_image:
            return {
                "status": "error",
                "vision_response": "Screen capture unavailable in current desktop session.",
                "voice_response": "I was unable to capture your screen display."
            }

        payload = {
            "model": active_vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": clean_prompt,
                    "images": [b64_image]
                }
            ],
            "stream": False,
            "keep_alive": "2m",
            "options": {"temperature": 0.2, "num_predict": 128}
        }

        try:
            resp = requests.post(f"{self.ollama_host}/api/chat", json=payload, timeout=45)
            if resp.status_code == 200:
                answer = resp.json().get("message", {}).get("content", "").strip()
                return {
                    "status": "analyzed",
                    "vision_response": answer,
                    "voice_response": answer
                }
        except Exception as e:
            print(f"[ModelManager Vision Inference Error]: {e}")

        return {
            "status": "error",
            "vision_response": "Vision model inference timed out.",
            "voice_response": "I could not complete the visual screen inspection."
        }
