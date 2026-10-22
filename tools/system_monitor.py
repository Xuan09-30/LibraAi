import os
import sys
import ctypes
from ctypes import wintypes
import subprocess
from typing import Dict, Any, List, Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


ALLOWLISTED_DIAGNOSTICS = {
    "network_info": ["ipconfig"],
    "gpu_status": ["nvidia-smi"],
    "top_processes": ["tasklist"],
    "ping_gateway": ["ping", "-n", "1", "1.1.1.1"],
    "system_info": ["systeminfo"]
}


class SystemMonitor:
    """
    Sandboxed system diagnostics, window enumeration, and hardware telemetry engine.
    Enforces strict read-only execution with 3.0-second timeout loop breakers.
    """

    def __init__(self, timeout: float = 3.0):
        self.timeout = timeout

    def get_system_metrics(self) -> Dict[str, Any]:
        """
        Retrieves CPU, RAM, and NVIDIA GPU metrics.
        Returns a dictionary with numeric values and a spoken-friendly summary.
        """
        metrics: Dict[str, Any] = {
            "cpu_percent": 0.0,
            "ram_used_gb": 0.0,
            "ram_total_gb": 0.0,
            "ram_percent": 0.0,
            "gpu_util_percent": None,
            "gpu_vram_used_mb": None,
            "gpu_vram_total_mb": None,
            "gpu_temp_c": None,
            "summary": ""
        }

        # 1. CPU & RAM via psutil
        if PSUTIL_AVAILABLE:
            try:
                metrics["cpu_percent"] = round(psutil.cpu_percent(interval=0.1), 1)
                vm = psutil.virtual_memory()
                metrics["ram_used_gb"] = round(vm.used / (1024 ** 3), 1)
                metrics["ram_total_gb"] = round(vm.total / (1024 ** 3), 1)
                metrics["ram_percent"] = round(vm.percent, 1)
            except Exception as e:
                print(f"[SystemMonitor psutil Warning]: {e}")

        # 2. GPU metrics via nvidia-smi with 2.0s timeout (CREATE_NO_WINDOW prevents flashing CMD popup)
        try:
            extra_flags = {}
            if sys.platform == "win32":
                extra_flags["creationflags"] = subprocess.CREATE_NO_WINDOW
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=2.0,
                shell=False,
                **extra_flags
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                if len(parts) >= 4:
                    metrics["gpu_util_percent"] = float(parts[0])
                    metrics["gpu_vram_used_mb"] = float(parts[1])
                    metrics["gpu_vram_total_mb"] = float(parts[2])
                    metrics["gpu_temp_c"] = float(parts[3])
        except Exception:
            # Non-blocking graceful fallback if no NVIDIA GPU or not on PATH
            pass

        # Build human-readable summary
        parts_str = [
            f"CPU is at {metrics['cpu_percent']}%",
            f"RAM usage is {metrics['ram_used_gb']} of {metrics['ram_total_gb']} gigabytes ({metrics['ram_percent']}%)"
        ]
        if metrics["gpu_util_percent"] is not None:
            vram_gb = round(metrics["gpu_vram_used_mb"] / 1024.0, 1)
            total_vram_gb = round(metrics["gpu_vram_total_mb"] / 1024.0, 1)
            parts_str.append(
                f"GPU utilization is {int(metrics['gpu_util_percent'])}% at {int(metrics['gpu_temp_c'])} degrees Celsius with {vram_gb} of {total_vram_gb} gigabytes VRAM used"
            )

        metrics["summary"] = ", and ".join(parts_str) + "."
        return metrics

    def list_open_windows(self) -> List[str]:
        """
        Enumerates visible application window titles using Win32 EnumWindows.
        Filters out background utility windows and empty titles.
        """
        if sys.platform != "win32":
            return []

        titles: List[str] = []
        ignored_titles = {
            "Program Manager", "Settings", "Default IME", "MSCTFIME UI",
            "Windows Input Experience", "Taskbar", "Search"
        }

        def enum_windows_proc(hwnd, lParam):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.strip()
                    if title and title not in ignored_titles and title not in titles:
                        titles.append(title)
            return True

        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        try:
            ctypes.windll.user32.EnumWindows(EnumWindowsProc(enum_windows_proc), 0)
        except Exception as e:
            print(f"[SystemMonitor EnumWindows Warning]: {e}")

        return titles

    def run_safe_diagnostic(self, command_key: str) -> str:
        """
        Executes strictly allowlisted read-only system checks with a hard timeout.
        Returns output truncated to 1,000 characters.
        """
        if command_key not in ALLOWLISTED_DIAGNOSTICS:
            return f"Error: Diagnostic command '{command_key}' is not in the allowlist."

        cmd = ALLOWLISTED_DIAGNOSTICS[command_key]
        try:
            extra_flags = {}
            if sys.platform == "win32":
                extra_flags["creationflags"] = subprocess.CREATE_NO_WINDOW
            res = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                **extra_flags
            )
            output = (res.stdout or res.stderr or "").strip()
            return output[:1000]
        except subprocess.TimeoutExpired:
            return f"Diagnostic check for '{command_key}' timed out after {self.timeout}s."
        except Exception as e:
            return f"Diagnostic execution error: {e}"
