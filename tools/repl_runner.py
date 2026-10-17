import os
import io
import time
import threading
import contextlib
import traceback
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

try:
    from IPython.core.interactiveshell import InteractiveShell
    IPYTHON_AVAILABLE = True
except ImportError:
    InteractiveShell = None
    IPYTHON_AVAILABLE = False

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class PersistentDataREPL:
    """
    Singleton thread-safe wrapper around IPython.core.interactiveshell.InteractiveShell.instance()
    (with isolated persistent namespace fallback) for Project Libra v8.0.
    Pre-seeds workspace with `numpy as np`, `pandas as pd`, `matplotlib.pyplot as plt`, and `seaborn as sns`.
    """

    _instance: Optional["PersistentDataREPL"] = None
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        with self._lock:
            if getattr(self, "_initialized", False):
                return
            self._initialized = True
            self.shell = None
            self.user_ns: Dict[str, Any] = {}

            if IPYTHON_AVAILABLE and InteractiveShell is not None:
                try:
                    self.shell = InteractiveShell.instance()
                    self.user_ns = self.shell.user_ns
                except Exception:
                    self.shell = None
                    self.user_ns = {}

            self._seed_scientific_imports()
            self._baseline_keys = set(self.user_ns.keys())

    def _seed_scientific_imports(self):
        """Ensures core scientific libraries are always present in the persistent namespace."""
        self.user_ns["np"] = np
        self.user_ns["pd"] = pd
        self.user_ns["plt"] = plt
        self.user_ns["sns"] = sns
        self.user_ns["os"] = os

    def set_variable(self, var_name: str, value: Any):
        """Injects a variable (e.g. `df`, `model`) into the persistent REPL namespace."""
        with self._lock:
            self.user_ns[var_name] = value

    def get_variable(self, var_name: str, default: Any = None) -> Any:
        """Retrieves any persisted object (`df`, `model`, etc.) from `user_ns`."""
        with self._lock:
            return self.user_ns.get(var_name, default)

    def list_active_dataframes(self) -> Dict[str, Dict[str, Any]]:
        """Returns active DataFrame shapes, column lists, and memory footprint in KB."""
        with self._lock:
            dfs: Dict[str, Dict[str, Any]] = {}
            for k, v in self.user_ns.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, pd.DataFrame):
                    mem_kb = round(float(v.memory_usage(deep=True).sum()) / 1024.0, 2)
                    dfs[k] = {
                        "shape": (int(v.shape[0]), int(v.shape[1])),
                        "rows": int(v.shape[0]),
                        "cols": int(v.shape[1]),
                        "columns": [str(c) for c in v.columns],
                        "memory_kb": mem_kb
                    }
            return dfs

    # Backward-compatible alias
    def list_dataframes(self) -> Dict[str, Dict[str, Any]]:
        return self.list_active_dataframes()

    def reset_namespace(self):
        """Resets user variables while keeping scientific imports (`np`, `pd`, `plt`, `sns`) active."""
        with self._lock:
            keys_to_remove = [
                k for k in list(self.user_ns.keys())
                if k not in self._baseline_keys and k not in ("np", "pd", "plt", "sns", "os")
            ]
            for k in keys_to_remove:
                self.user_ns.pop(k, None)
            self._seed_scientific_imports()

    def run_code(self, code: str, timeout_sec: float = 12.0) -> Dict[str, Any]:
        """
        Redirects `stdout` and `stderr`, runs `code` in the persistent namespace,
        and returns:
        {
            "status": "success" | "error",
            "stdout": str,
            "stderr": str,
            "result": Any,
            "error": str | None,
            "duration_ms": float,
            "dataframes": dict,
            "variables": dict
        }
        """
        clean_code = (code or "").strip()
        if not clean_code:
            return {
                "status": "success",
                "stdout": "",
                "stderr": "",
                "result": None,
                "error": None,
                "duration_ms": 0.0,
                "dataframes": self.list_active_dataframes(),
                "variables": {}
            }

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        t0 = time.perf_counter()

        exec_result = None
        error_msg = None

        with self._lock:
            self._seed_scientific_imports()
            try:
                with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                    if self.shell is not None:
                        res = self.shell.run_cell(clean_code, store_history=True, silent=False)
                        if res.error_before_exec:
                            error_msg = f"{type(res.error_before_exec).__name__}: {res.error_before_exec}"
                        elif res.error_in_exec:
                            error_msg = f"{type(res.error_in_exec).__name__}: {res.error_in_exec}"
                        else:
                            exec_result = res.result
                    else:
                        # Isolated persistent namespace fallback
                        lines = clean_code.splitlines()
                        if lines:
                            try:
                                # If last line is an expression, evaluate and return it
                                if len(lines) > 1:
                                    exec("\n".join(lines[:-1]), self.user_ns)
                                try:
                                    exec_result = eval(lines[-1], self.user_ns)
                                except SyntaxError:
                                    exec(lines[-1], self.user_ns)
                            except Exception:
                                exec(clean_code, self.user_ns)
            except Exception as exc:
                error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        out_text = stdout_buf.getvalue().strip()
        err_text = stderr_buf.getvalue().strip()

        tracked_vars = {}
        with self._lock:
            for k, v in self.user_ns.items():
                if k.startswith("_") or k in self._baseline_keys or k in ("In", "Out", "exit", "quit", "get_ipython"):
                    continue
                if isinstance(v, (int, float, str, bool, np.number)):
                    tracked_vars[k] = float(v) if isinstance(v, np.floating) else (int(v) if isinstance(v, np.integer) else v)
                elif isinstance(v, (list, dict, tuple)) and len(v) <= 50:
                    tracked_vars[k] = v

        status = "error" if error_msg else "success"
        return {
            "status": status,
            "stdout": out_text,
            "stderr": err_text,
            "result": exec_result,
            "error": error_msg,
            "duration_ms": duration_ms,
            "elapsed_sec": round(duration_ms / 1000.0, 4),
            "dataframes": self.list_active_dataframes(),
            "variables": tracked_vars
        }
