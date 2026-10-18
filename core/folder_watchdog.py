import os
import sys
import time
import threading
from typing import Dict, Any, List, Optional, Callable, Set

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


class DebouncedEventHandler(FileSystemEventHandler):
    """
    Thread-safe debouncing event handler for filesystem modifications.
    Collapses multiple rapid file creation/modification events into a single callback.
    """

    def __init__(self, callback: Callable[[str, str], None], delay: float = 1.2):
        super().__init__()
        self.callback = callback
        self.delay = delay
        self._timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _trigger(self, path: str, event_type: str):
        with self._lock:
            self._timers.pop(path, None)
        try:
            self.callback(path, event_type)
        except Exception as e:
            print(f"[FolderWatchdog Callback Error]: {e}")

    def _debounce(self, path: str, event_type: str):
        with self._lock:
            existing = self._timers.get(path)
            if existing:
                existing.cancel()
            timer = threading.Timer(self.delay, self._trigger, args=[path, event_type])
            self._timers[path] = timer
            timer.daemon = True
            timer.start()

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory:
            self._debounce(event.src_path, "created")

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory:
            self._debounce(event.src_path, "modified")

    def on_moved(self, event: FileSystemEvent):
        if not event.is_directory:
            dest = getattr(event, "dest_path", event.src_path)
            self._debounce(dest, "moved")

    def on_deleted(self, event: FileSystemEvent):
        if not event.is_directory:
            self._debounce(event.src_path, "deleted")


class AutomatedFolderWatchdog:
    """
    Dual-Category Autonomous Folder Watchdog Engine (v11.0).
    Monitors Windows program directories (Start Menu, Desktop, Local Programs)
    and document directories (Documents, Downloads, Workspace).
    - Programs: On .lnk, .url, or .exe change -> Debounced refresh of GameDiscoveryEngine.
    - Documents: On text/code/PDF file change -> Debounced ingestion into Document RAG.
    Runs non-blocking in background daemon threads with polling fallback.
    """

    PROGRAM_EXTENSIONS: Set[str] = {".lnk", ".url", ".exe", ".appref-ms"}
    DOCUMENT_EXTENSIONS: Set[str] = {
        ".pdf", ".docx", ".txt", ".py", ".c", ".cpp", ".h", ".cs",
        ".md", ".json", ".csv", ".log", ".yaml", ".yml", ".html"
    }

    def __init__(
        self,
        discovery_engine: Optional[Any] = None,
        document_rag: Optional[Any] = None,
        custom_program_dirs: Optional[List[str]] = None,
        custom_document_dirs: Optional[List[str]] = None,
        event_callback: Optional[Callable[[str, str, str], None]] = None,
    ):
        self.discovery_engine = discovery_engine
        self.document_rag = document_rag
        self.event_callback = event_callback

        self.program_dirs = self._resolve_program_dirs(custom_program_dirs)
        self.document_dirs = self._resolve_document_dirs(custom_document_dirs)

        self._observer: Optional[Any] = None
        self._running = False
        self._polling_thread: Optional[threading.Thread] = None

        self.stats = {
            "is_running": False,
            "program_dirs_monitored": len(self.program_dirs),
            "document_dirs_monitored": len(self.document_dirs),
            "program_events_count": 0,
            "document_events_count": 0,
            "last_event_time": None,
            "last_event_path": None,
        }

    def _resolve_program_dirs(self, custom: Optional[List[str]]) -> List[str]:
        dirs = []
        if custom:
            dirs.extend(custom)
        else:
            candidates = [
                r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
                os.path.expanduser(r"~\AppData\Roaming\Microsoft\Windows\Start Menu\Programs"),
                os.path.expanduser(r"~\Desktop"),
                os.path.expanduser(r"~\OneDrive\Desktop"),
                r"C:\Users\Public\Desktop",
                os.path.expanduser(r"~\AppData\Local\Programs"),
            ]
            for c in candidates:
                if c and os.path.isdir(c) and c not in dirs:
                    dirs.append(os.path.abspath(c))
        return dirs

    def _resolve_document_dirs(self, custom: Optional[List[str]]) -> List[str]:
        dirs = []
        if custom:
            dirs.extend(custom)
        else:
            candidates = [
                os.path.expanduser(r"~\Documents"),
                os.path.expanduser(r"~\OneDrive\Documents"),
                os.path.expanduser(r"~\Downloads"),
            ]
            for c in candidates:
                if c and os.path.isdir(c) and c not in dirs:
                    dirs.append(os.path.abspath(c))
        return dirs

    def _handle_program_event(self, path: str, event_type: str):
        ext = os.path.splitext(path)[1].lower()
        if ext not in self.PROGRAM_EXTENSIONS:
            return

        filename = os.path.basename(path)
        # Skip temp / uninstaller shortcuts
        if any(sw in filename.lower() for sw in ("unins", "update", "temp", "tmp", "~$")):
            return

        self.stats["program_events_count"] += 1
        self.stats["last_event_time"] = time.time()
        self.stats["last_event_path"] = path

        print(f"[FolderWatchdog] Program change detected ({event_type}): {filename}")

        if self.discovery_engine and hasattr(self.discovery_engine, "refresh"):
            try:
                self.discovery_engine.refresh()
                count = len(getattr(self.discovery_engine, "apps", {}))
                print(f"[FolderWatchdog] Discovered apps refreshed. {count} apps currently indexed.")
            except Exception as e:
                print(f"[FolderWatchdog Discovery Refresh Error]: {e}")

        if self.event_callback:
            try:
                self.event_callback("program", path, event_type)
            except Exception:
                pass

    def _handle_document_event(self, path: str, event_type: str):
        if event_type == "deleted":
            return

        ext = os.path.splitext(path)[1].lower()
        if ext not in self.DOCUMENT_EXTENSIONS:
            return

        filename = os.path.basename(path)
        if filename.startswith((".", "~$")) or filename.endswith(".tmp"):
            return

        self.stats["document_events_count"] += 1
        self.stats["last_event_time"] = time.time()
        self.stats["last_event_path"] = path

        print(f"[FolderWatchdog] Document change detected ({event_type}): {filename}")

        if self.document_rag and hasattr(self.document_rag, "ingest_file") and os.path.isfile(path):
            try:
                self.document_rag.ingest_file(path)
                print(f"[FolderWatchdog] Ingested {filename} into Document RAG.")
            except Exception as e:
                print(f"[FolderWatchdog RAG Ingestion Error]: {e}")

        if self.event_callback:
            try:
                self.event_callback("document", path, event_type)
            except Exception:
                pass

    def start(self):
        """Starts monitoring in non-blocking background threads."""
        if self._running:
            return

        self._running = True
        self.stats["is_running"] = True

        if WATCHDOG_AVAILABLE:
            try:
                self._observer = Observer()
                prog_handler = DebouncedEventHandler(self._handle_program_event, delay=1.2)
                for p_dir in self.program_dirs:
                    if os.path.isdir(p_dir):
                        try:
                            self._observer.schedule(prog_handler, path=p_dir, recursive=True)
                        except Exception as sched_err:
                            print(f"[FolderWatchdog Warning] Could not watch program dir {p_dir}: {sched_err}")

                doc_handler = DebouncedEventHandler(self._handle_document_event, delay=1.5)
                for d_dir in self.document_dirs:
                    if os.path.isdir(d_dir):
                        try:
                            self._observer.schedule(doc_handler, path=d_dir, recursive=False)
                        except Exception as sched_err:
                            print(f"[FolderWatchdog Warning] Could not watch doc dir {d_dir}: {sched_err}")

                self._observer.daemon = True
                self._observer.start()
                print(f"[FolderWatchdog] Watchdog observer online. Monitoring {len(self.program_dirs)} program dirs & {len(self.document_dirs)} document dirs.")
            except Exception as obs_err:
                print(f"[FolderWatchdog Observer Init Error]: {obs_err}. Falling back to polling sweep.")
                self._start_polling_fallback()
        else:
            self._start_polling_fallback()

    def _start_polling_fallback(self):
        """Runs a periodic polling sweep every 30 seconds if native filesystem observer is unavailable."""
        def _poll_loop():
            last_check = time.time()
            while self._running:
                time.sleep(30.0)
                if not self._running:
                    break
                now = time.time()
                for p_dir in self.program_dirs:
                    if not os.path.isdir(p_dir):
                        continue
                    try:
                        for entry in os.scandir(p_dir):
                            if entry.is_file() and os.path.splitext(entry.name)[1].lower() in self.PROGRAM_EXTENSIONS:
                                if entry.stat().st_mtime > last_check:
                                    self._handle_program_event(entry.path, "polled_change")
                    except OSError:
                        continue
                last_check = now

        self._polling_thread = threading.Thread(target=_poll_loop, daemon=True, name="FolderWatchdogPollingFallback")
        self._polling_thread.start()

    def stop(self):
        """Stops the watchdog observer and background threads."""
        self._running = False
        self.stats["is_running"] = False
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception:
                pass
            self._observer = None

    def get_status(self) -> Dict[str, Any]:
        """Returns the current runtime telemetry of the folder watchdog."""
        info = dict(self.stats)
        info["program_directories"] = list(self.program_dirs)
        info["document_directories"] = list(self.document_dirs)
        return info
