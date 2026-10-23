import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.system_monitor import SystemMonitor, ALLOWLISTED_DIAGNOSTICS
from core.vram_governor import VRAMAutoGovernor, get_vram_governor

__all__ = ["SystemMonitor", "ALLOWLISTED_DIAGNOSTICS", "VRAMAutoGovernor", "get_vram_governor"]
