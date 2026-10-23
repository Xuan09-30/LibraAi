import os
import sys
import time
import threading
import requests
from typing import Set, List, Optional, Dict, Any

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.telemetry import profiler


class VRAMAutoGovernor:
    """
    VRAM Auto-Governor & 'Zero-Stutter Gaming Shield' (v11.0 / Phase 11).
    Runs a 2.0-second background polling worker checking for competitive game processes.
    When detected:
      - Immediately sends keep_alive: 0 to Ollama (qwen3:8b, qwen2.5vl:7b) to reclaim ~6-8GB VRAM.
      - Sets internal state to GAMING_LITE_MODE = True:
        * Spatial vision downgrades strictly to CPU ONNX RapidOCR (bypassing GPU vision models).
        * LLM queries route through fast-path regex cache or ultra-lightweight fallback.
    When all game processes exit:
      - Asynchronously warms up qwen3:8b with keep_alive: 24h.
      - Restores full cognitive multimodal engine without restarting the application.
    """

    TARGET_GAMES: Set[str] = {
        "valorant.exe",
        "overwatch.exe",
        "apex.exe",
        "r5apex.exe",
        "cs2.exe",
        "league of legends.exe"
    }

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(VRAMAutoGovernor, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, ollama_url: str = "http://localhost:11434", poll_interval: float = 2.0):
        if getattr(self, "_initialized", False):
            return
        self.ollama_url = ollama_url.rstrip("/")
        self.poll_interval = poll_interval
        self.gaming_lite_mode = False
        self.active_games: List[str] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._initialized = True

    def start(self):
        """Starts the background 2.0s polling daemon."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="VRAMGovernorWorker")
        self._thread.start()
        print("[VRAM Governor] Zero-Stutter Gaming Shield active (2.0s polling).")

    def stop(self):
        """Stops the monitoring loop."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def is_gaming_lite_mode(self) -> bool:
        """Returns True if Gaming Lite Mode is currently active."""
        with self._lock:
            return self.gaming_lite_mode

    def check_running_games(self) -> List[str]:
        """Scans system processes for target games."""
        if not PSUTIL_AVAILABLE:
            return []
        found = []
        try:
            for proc in psutil.process_iter(["name"]):
                try:
                    pname = (proc.info.get("name") or "").lower().strip()
                    if pname in self.TARGET_GAMES:
                        found.append(pname)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            print(f"[VRAM Governor Scan Warning]: {e}")
        return list(set(found))

    def flush_vram_for_gaming(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Immediately flushes qwen3:8b and qwen2.5vl:7b from GPU VRAM.
        """
        results = {}
        models_to_flush = ["qwen3:8b", "qwen2.5vl:7b", "qwen2.5-coder:7b"]
        for m in models_to_flush:
            if dry_run:
                results[m] = "dry_run_flushed"
                continue
            try:
                resp = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": m, "keep_alive": 0},
                    timeout=3.0
                )
                results[m] = "flushed" if resp.status_code == 200 else f"failed_{resp.status_code}"
            except Exception as e:
                results[m] = f"error_{e}"

        print(f"[VRAM Governor] GAMING_LITE_MODE ACTIVATED: Flushed {models_to_flush} from VRAM.")
        return results

    def warmup_models_after_gaming(self, dry_run: bool = False):
        """
        Asynchronously warms up qwen3:8b back into GPU VRAM.
        """
        def _warm():
            if dry_run:
                return
            try:
                # Preload qwen3:8b with 24h keep-alive
                requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": "qwen3:8b", "keep_alive": "24h"},
                    timeout=10.0
                )
                print("[VRAM Governor] GAMING_LITE_MODE DEACTIVATED: Restored qwen3:8b into VRAM.")
            except Exception as e:
                print(f"[VRAM Governor Warmup Warning]: {e}")

        threading.Thread(target=_warm, daemon=True).start()

    @property
    def gaming_mode(self) -> bool:
        return self.is_gaming_lite_mode()

    def step_cycle(self):
        """Executes a single synchronous evaluation pass of the governor."""
        games = self.check_running_games()
        with self._lock:
            if games and not self.gaming_lite_mode:
                self.gaming_lite_mode = True
                self.active_games = games
                self.flush_vram_for_gaming()
            elif not games and self.gaming_lite_mode:
                self.gaming_lite_mode = False
                self.active_games = []
                self.warmup_models_after_gaming()

    def _monitor_loop(self):
        while self._running:
            try:
                self.step_cycle()
            except Exception as e:
                print(f"[VRAM Governor Loop Error]: {e}")

            time.sleep(self.poll_interval)


# Global singleton accessor
def get_vram_governor() -> VRAMAutoGovernor:
    return VRAMAutoGovernor()
