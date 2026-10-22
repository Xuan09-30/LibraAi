import os
import sys
import time
import ast
import threading
from typing import Callable, Optional, Dict

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


class CodeChangeHandler(FileSystemEventHandler):
    """
    Watches source code changes (.py, .html) across project directories.
    Debounces rapid edits, tracks file modification timestamps, validates syntax for python files,
    and notifies the reload callback.
    """

    EXCLUDED_DIRS = {
        "logs", "venv", ".git", "__pycache__", ".pytest_cache", ".vscode", ".idea",
        "assets/memory", ".user_uploaded", "temp", "tmp"
    }

    EXCLUDED_FILES = {
        "three.min.js", "three.js", "vconsole.min.js"
    }

    WATCHED_EXTENSIONS = {".py", ".html"}

    def __init__(self, reload_callback: Callable[[str], None], debounce_sec: float = 1.5):
        super().__init__()
        self.reload_callback = reload_callback
        self.debounce_sec = debounce_sec
        self._timer: Optional[threading.Timer] = None
        self._pending_file: Optional[str] = None
        self._lock = threading.Lock()
        self._mtimes: Dict[str, float] = {}
        self._start_time = time.time()

    def _is_relevant_path(self, path: str) -> bool:
        norm = os.path.normpath(path).replace("\\", "/")
        parts = norm.split("/")

        # Exclude temporary or hidden files
        basename = os.path.basename(norm)
        if basename in self.EXCLUDED_FILES:
            return False
        if basename.startswith(".") or basename.startswith("~") or basename.endswith(".tmp") or basename.endswith(".swp"):
            return False

        # Exclude blacklisted directories
        for excl in self.EXCLUDED_DIRS:
            if excl in parts:
                return False

        # Check file extension
        _, ext = os.path.splitext(norm)
        if ext.lower() not in self.WATCHED_EXTENSIONS:
            return False

        return True

    def _validate_file(self, filepath: str) -> bool:
        if not os.path.exists(filepath):
            return False
        # If it's a python file, verify that it compiles cleanly without syntax errors
        if filepath.endswith(".py"):
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if not content.strip():
                    return False
                ast.parse(content, filename=filepath)
                return True
            except SyntaxError as syn_err:
                print(f"[CodeReloader] Syntax error in {filepath}: {syn_err}. Waiting for file fix before reload.")
                return False
            except Exception:
                return True
        return True

    def _trigger(self):
        with self._lock:
            target = self._pending_file
            self._pending_file = None
            self._timer = None

        if target and self._validate_file(target):
            try:
                self.reload_callback(target)
            except Exception as e:
                print(f"[CodeReloader] Error invoking reload callback: {e}")

    def _debounce(self, filepath: str):
        if not self._is_relevant_path(filepath):
            return

        try:
            mtime = os.path.getmtime(filepath)
            with self._lock:
                # If first time seeing this file, record its baseline mtime
                if filepath not in self._mtimes:
                    self._mtimes[filepath] = mtime
                    # If file has not actually been modified since reloader started, ignore startup access
                    if mtime <= self._start_time + 1.0:
                        return

                prev_mtime = self._mtimes.get(filepath, 0.0)
                # If mtime didn't advance by at least 0.1s, ignore (e.g. read access or metadata query)
                if mtime - prev_mtime < 0.1:
                    return
                self._mtimes[filepath] = mtime
                self._pending_file = filepath
                if self._timer:
                    self._timer.cancel()
                self._timer = threading.Timer(self.debounce_sec, self._trigger)
                self._timer.daemon = True
                self._timer.start()
        except OSError:
            pass

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory:
            self._debounce(event.src_path)

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory:
            self._debounce(event.src_path)


class CodeReloader:
    """
    Background observer that monitors project source files and triggers
    an application restart when verified code changes occur.
    """

    def __init__(self, root_dir: str, reload_callback: Callable[[str], None], debounce_sec: float = 1.5):
        self.root_dir = os.path.abspath(root_dir)
        self.reload_callback = reload_callback
        self.debounce_sec = debounce_sec
        self.observer: Optional[Observer] = None
        self.handler: Optional[CodeChangeHandler] = None

    def start(self):
        if not WATCHDOG_AVAILABLE:
            print("[CodeReloader Warning]: watchdog package not installed. Auto-reload disabled.")
            return

        self.handler = CodeChangeHandler(self.reload_callback, debounce_sec=self.debounce_sec)
        self.observer = Observer()
        self.observer.schedule(self.handler, self.root_dir, recursive=True)
        self.observer.daemon = True
        self.observer.start()
        print(f"[CodeReloader] Live source code monitoring online ({self.root_dir}).")

    def stop(self):
        if self.observer and self.observer.is_alive():
            try:
                self.observer.stop()
                self.observer.join(timeout=1.0)
            except Exception:
                pass
