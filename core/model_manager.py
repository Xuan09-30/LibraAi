import os
import io
import re
import json
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

    @staticmethod
    def _attach_thread_desktop():
        """Attaches calling thread to interactive input desktop on Windows."""
        import sys
        import ctypes
        if sys.platform == "win32" and hasattr(ctypes, "windll"):
            try:
                user32 = ctypes.windll.user32
                hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
                if hdesk:
                    user32.SetThreadDesktop(hdesk)
            except Exception:
                pass

    @staticmethod
    def _get_active_window_bbox() -> Optional[tuple]:
        """Captures the bounding box of the active foreground window on Windows."""
        import sys
        import ctypes
        if sys.platform != "win32" or not hasattr(ctypes, "windll"):
            return None
        try:
            ModelManager._attach_thread_desktop()
            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long)
                ]

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                hwnd = user32.GetTopWindow(0)
            if not hwnd:
                return None
            rect = RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if width > 60 and height > 60:
                    return (max(0, rect.left), max(0, rect.top), rect.right, rect.bottom)
        except Exception as e:
            print(f"[ActiveWindow BBox Warning]: {e}")
        return None

    @staticmethod
    def capture_screenshot(bbox: Optional[tuple] = None):
        """
        Captures the screen in an isolated clean worker thread with desktop attachment.
        This completely bypasses Windows Win32 ERROR_BUSY (170) when GUI/Qt threads
        have already created window handles. Falls back to mss if needed.
        """
        import threading
        capture_result = {"image": None, "error": None}

        def _isolated_grab():
            try:
                import ctypes
                import sys
                from PIL import ImageGrab

                if sys.platform == "win32" and hasattr(ctypes, "windll"):
                    user32 = ctypes.windll.user32
                    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
                    if hdesk:
                        user32.SetThreadDesktop(hdesk)

                img = ImageGrab.grab(bbox=bbox)
                capture_result["image"] = img
            except Exception as ex:
                try:
                    import mss
                    from PIL import Image
                    with mss.MSS() as sct:
                        mon = sct.monitors[1]
                        sct_img = sct.grab(mon)
                        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                        if bbox:
                            img = img.crop(bbox)
                        capture_result["image"] = img
                except Exception as mss_ex:
                    capture_result["error"] = ex

        grab_thread = threading.Thread(target=_isolated_grab, daemon=True)
        grab_thread.start()
        grab_thread.join(timeout=3.5)

        return capture_result.get("image")

    def analyze_screen(self, prompt: str = "", active_window_only: bool = False, window_info: Optional[Dict[str, Any]] = None, dry_run: bool = False) -> Dict[str, Any]:
        """
        Captures the active foreground window or primary display and analyzes it using qwen2.5vl:7b.
        Integrates ground-truth active window metadata to prevent any hallucinations.
        """
        clean_prompt = prompt or "Describe what you see on the screen concisely in 1-2 spoken sentences."
        target_scope = "active window" if active_window_only else "full screen"

        if dry_run:
            app_lbl = window_info.get("app_label", "desktop") if window_info else "desktop"
            return {
                "status": "analyzed",
                "scope": target_scope,
                "vision_response": f"[Dry Run] Screen ({target_scope}) analyzed for: {clean_prompt}",
                "voice_response": f"I can see {app_lbl} on your screen."
            }

        vision_spec = self.acquire_model("vision", dry_run=False)
        active_vision_model = vision_spec["active_model"]

        # Capture screenshot using isolated worker thread
        b64_image = None
        try:
            bbox = self._get_active_window_bbox() if active_window_only else None
            screenshot = self.capture_screenshot(bbox=bbox)
            if screenshot:
                if screenshot.width > 1280:
                    scale = 1280.0 / screenshot.width
                    new_size = (1280, int(screenshot.height * scale))
                    screenshot = screenshot.resize(new_size)

                buffer = io.BytesIO()
                screenshot.save(buffer, format="JPEG", quality=85)
                b64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
            else:
                print("[ModelManager Screen Capture Warning]: Screenshot returned None from worker thread.")
        except Exception as e:
            print(f"[ModelManager Screen Capture Warning]: {e}")

        # Grounding context from window_info
        grounding_context = ""
        app_lbl = "application"
        if window_info:
            app_lbl = window_info.get("app_label") or "application"
            w_title = window_info.get("window_title") or ""
            grounding_context = f"Ground Truth: The user currently has {app_lbl} active (window title: '{w_title}').\n"

        if not b64_image:
            if window_info and window_info.get("window_title"):
                return {
                    "status": "partial",
                    "vision_response": f"Screen capture failed, but detected active window {app_lbl}: '{window_info.get('window_title')}'.",
                    "voice_response": f"I see {app_lbl} active on your screen with title '{window_info.get('window_title')}', though visual screenshot was blocked."
                }
            return {
                "status": "error",
                "vision_response": "Screen capture unavailable in current desktop session.",
                "voice_response": "I was unable to capture your screen display."
            }

        vision_instruction = (
            f"{grounding_context}"
            f"User Query: {clean_prompt}\n"
            "Guidelines: Answer in 1-2 spoken sentences. State accurately what is visible on the screen. "
            "If the user asks for their in-game name, username, or fine text, inspect the screenshot carefully. "
            "If the text is clearly legible, state it exactly. If it is blurry, small, occluded, or not visible, "
            "truthfully state that you cannot clearly read the name or text on screen. "
            "NEVER invent, guess, or hallucinate names, windows, or folders."
        )

        payload = {
            "model": active_vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": vision_instruction,
                    "images": [b64_image]
                }
            ],
            "stream": False,
            "keep_alive": "2m",
            "options": {"temperature": 0.1, "num_predict": 120}
        }

        try:
            resp = requests.post(f"{self.ollama_host}/api/chat", json=payload, timeout=45)
            if resp.status_code == 200:
                answer = resp.json().get("message", {}).get("content", "").strip()
                # Clean any markdown or thought tokens if present
                answer = answer.replace("<think>", "").replace("</think>", "").strip()
                return {
                    "status": "analyzed",
                    "vision_response": answer,
                    "voice_response": answer
                }
        except Exception as e:
            print(f"[ModelManager Vision Inference Error]: {e}")

        # Truthful fallback if inference timed out
        if window_info and window_info.get("window_title"):
            fallback_voice = f"I see {app_lbl} active on your screen (title: '{window_info.get('window_title')}'). Deep visual reasoning timed out."
        else:
            fallback_voice = "I could not complete the visual screen inspection."

        return {
            "status": "error",
            "vision_response": "Vision model inference timed out or failed.",
            "voice_response": fallback_voice
        }

    def locate_ui_mark(
        self,
        prompt: str,
        mark_dict: Dict[int, Dict[str, Any]],
        som_image_path: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Locates the mark ID matching the user's intent using Set-of-Mark visual reasoning
        with qwen2.5vl:7b, backed by lexical element matching fallback.
        Ensures strict 2m keep_alive to release VRAM immediately after inference.
        """
        if not mark_dict:
            return {"status": "error", "message": "No marks available", "mark_id": None}

        # 1. Exact / Substring name heuristic match (instant <1ms CPU check)
        p_lower = prompt.lower()
        direct_mark = re.search(r"\bmark\s+(\d+)\b", p_lower)
        if direct_mark:
            mid = int(direct_mark.group(1))
            if mid in mark_dict:
                return {
                    "status": "located",
                    "mark_id": mid,
                    "target": mark_dict[mid],
                    "method": "direct_number"
                }

        for mid, mdata in mark_dict.items():
            name = (mdata.get("name") or "").lower().strip()
            if name and (name in p_lower or p_lower in name):
                return {
                    "status": "located",
                    "mark_id": mid,
                    "target": mdata,
                    "method": "name_match"
                }

        if dry_run:
            first_key = next(iter(mark_dict.keys()))
            return {
                "status": "located",
                "mark_id": first_key,
                "target": mark_dict[first_key],
                "method": "dry_run_fallback"
            }

        # 2. VLM Set-of-Mark Visual Grounding with qwen2.5vl:7b
        if som_image_path and os.path.exists(som_image_path):
            try:
                with open(som_image_path, "rb") as f:
                    b64_img = base64.b64encode(f.read()).decode("utf-8")

                vision_spec = self.acquire_model("vision", dry_run=False)
                active_vision_model = vision_spec.get("active_model", "qwen2.5vl:7b")

                system_prompt = (
                    "You are an expert GUI grounding agent. The user wants to click or interact with a UI element.\n"
                    "Inspect the attached image which has numbered badges [1], [2], [3], etc. highlighting interactable elements.\n"
                    "Select the single mark ID that best matches the user's intended target.\n"
                    "Respond ONLY with valid JSON in this format: {\"mark_id\": <integer>, \"reason\": \"<short reason>\"}."
                )

                payload = {
                    "model": active_vision_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"{system_prompt}\nUser request: '{prompt}'",
                            "images": [b64_img]
                        }
                    ],
                    "format": "json",
                    "stream": False,
                    "keep_alive": "2m",
                    "options": {"temperature": 0.0, "num_predict": 60}
                }

                resp = requests.post(f"{self.ollama_host}/api/chat", json=payload, timeout=30)
                if resp.status_code == 200:
                    raw_content = resp.json().get("message", {}).get("content", "").strip()
                    parsed = json.loads(raw_content)
                    chosen_id = parsed.get("mark_id")
                    if chosen_id is not None:
                        try:
                            chosen_id = int(chosen_id)
                            if chosen_id in mark_dict:
                                return {
                                    "status": "located",
                                    "mark_id": chosen_id,
                                    "target": mark_dict[chosen_id],
                                    "reason": parsed.get("reason", ""),
                                    "method": "vlm_grounding"
                                }
                        except (ValueError, TypeError):
                            pass
            except Exception as e:
                print(f"[ModelManager locate_ui_mark VLM Error]: {e}")

        # 3. Fallback to first candidate if VLM unreachable
        first_key = next(iter(mark_dict.keys()))
        return {
            "status": "located",
            "mark_id": first_key,
            "target": mark_dict[first_key],
            "method": "positional_fallback"
        }
