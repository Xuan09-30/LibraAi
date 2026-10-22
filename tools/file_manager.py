import os
import sys
import re
import shutil
import subprocess
from typing import Optional, Dict, Any, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class EverythingSearchEngine:
    """
    Sub-5ms System-Wide File Discovery via voidtools Everything CLI (es.exe) (Phase 7).
    Queries NTFS Master File Table (MFT) directly: `es.exe -n 20 -sort date-modified-descending <query>`.
    Falls back gracefully to fast scandir/pathlib searching when es.exe is absent.
    """
    def __init__(self, es_bin: Optional[str] = None):
        self.es_bin = es_bin

    def search(self, query: str, max_results: int = 20, sort_by_date: bool = True) -> List[str]:
        clean_q = (query or "").strip()
        if not clean_q:
            return []

        if self.es_bin and os.path.isfile(self.es_bin):
            try:
                cmd = [self.es_bin, "-n", str(max_results)]
                if sort_by_date:
                    cmd.extend(["-sort", "date-modified-descending"])
                cmd.append(clean_q)
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
                if res.returncode == 0:
                    lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                    valid_paths = [p for p in lines if os.path.exists(p)]
                    if valid_paths:
                        return valid_paths[:max_results]
            except Exception as e:
                print(f"[EverythingSearchEngine Warning]: {e}")

        # Fallback: fast search in standard User and Workspace root directories
        results = []
        user_dirs = [
            PROJECT_ROOT,
            os.path.expanduser("~\\Desktop"),
            os.path.expanduser("~\\Downloads"),
            os.path.expanduser("~\\Documents")
        ]
        q_lower = clean_q.lower()
        for root_dir in user_dirs:
            if not os.path.isdir(root_dir):
                continue
            try:
                for root, dirs, files in os.walk(root_dir):
                    dirs[:] = [d for d in dirs if d not in [".git", "venv", "__pycache__", "node_modules", "assets/memory"]]
                    for f in files:
                        if q_lower in f.lower():
                            results.append(os.path.join(root, f))
                            if len(results) >= max_results:
                                return results
            except Exception:
                continue
        return results


class FileManager:
    """
    Local filesystem and folder manager.
    Integrates with Voidtools Everything CLI (es.exe) for sub-second NTFS searches,
    with bounded multi-level fallbacks across user and system directories.
    """

    @staticmethod
    def _resolve_shell_dir(csidl: int, folder_name: str) -> str:
        """Resolves the real visible Windows directory accounting for OneDrive redirection."""
        user_home = os.path.expanduser("~")
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
                if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0:
                    val = buf.value
                    if val and os.path.isdir(val):
                        return os.path.normpath(val)
            except Exception:
                pass

        onedrive_path = os.path.join(user_home, "OneDrive", folder_name)
        if os.path.isdir(onedrive_path):
            return os.path.normpath(onedrive_path)

        return os.path.normpath(os.path.join(user_home, folder_name))

    @classmethod
    def get_real_desktop_path(cls) -> str:
        """Returns the true visible Windows 11 Desktop path (0x0010 = CSIDL_DESKTOPDIRECTORY)."""
        return cls._resolve_shell_dir(0x0010, "Desktop")

    def __init__(self, es_path: Optional[str] = None):
        self.es_bin = self._find_everything_cli(es_path)
        self.everything_bin = self._find_everything_app()
        self.everything_engine = EverythingSearchEngine(self.es_bin)
        user_home = os.path.expanduser("~")

        self.last_folder_path: Optional[str] = None
        self.last_folder_name: Optional[str] = None
        self.last_file_path: Optional[str] = None
        self.last_file_name: Optional[str] = None

        desktop_path = self.get_real_desktop_path()
        documents_path = self._resolve_shell_dir(0x0005, "Documents")
        pictures_path = self._resolve_shell_dir(0x0027, "Pictures")

        self.known_dirs: Dict[str, str] = {
            "desktop": desktop_path,
            "documents": documents_path,
            "downloads": os.path.join(user_home, "Downloads"),
            "pictures": pictures_path,
            "music": os.path.join(user_home, "Music"),
            "videos": os.path.join(user_home, "Videos"),
            "program files": os.environ.get("ProgramFiles", "C:\\Program Files"),
            "program file": os.environ.get("ProgramFiles", "C:\\Program Files"),
            "programs file": os.environ.get("ProgramFiles", "C:\\Program Files"),
            "programs files": os.environ.get("ProgramFiles", "C:\\Program Files"),
            "program files (x86)": os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            "program file (x86)": os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            "programs file (x86)": os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            "programs files (x86)": os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            "windows": os.environ.get("SystemRoot", "C:\\Windows"),
            "home": user_home,
            "user": user_home,
            "workspace": PROJECT_ROOT,
            "project": PROJECT_ROOT
        }

    def _find_everything_cli(self, custom_path: Optional[str] = None) -> Optional[str]:
        """Locates es.exe from custom path, PATH, or standard Program Files locations."""
        if custom_path and os.path.isfile(custom_path):
            return custom_path

        which_es = shutil.which("es.exe") or shutil.which("es")
        if which_es:
            return which_es

        candidates = [
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Everything", "es.exe"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Everything", "es.exe"),
            "C:\\Program Files (x86)\\Everything\\es.exe",
            "C:\\Program Files\\Everything\\es.exe"
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        return None

    def _find_everything_app(self) -> Optional[str]:
        """Locates Everything.exe from standard Program Files locations or PATH."""
        which_app = shutil.which("Everything.exe") or shutil.which("Everything")
        if which_app:
            return which_app

        candidates = [
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Everything", "Everything.exe"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Everything", "Everything.exe"),
            "C:\\Program Files (x86)\\Everything\\Everything.exe",
            "C:\\Program Files\\Everything\\Everything.exe"
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        return None

    def search_files_fast(self, query: str, max_results: int = 20) -> List[str]:
        """Sub-5ms system-wide file search via EverythingSearchEngine (Phase 7)."""
        return self.everything_engine.search(query, max_results=max_results)

    def search_path(self, query: str, folders_only: bool = True) -> Optional[str]:
        """
        Searches for a folder or file matching query.
        1. Strips conversational filler words and normalizes system folders.
        2. Checks known system/user directories.
        3. Executes Voidtools Everything CLI (es.exe) if present.
        4. Falls back to a fast bounded 2-level directory scan with fuzzy/condensed matching.
        """
        clean_q = query.strip()
        if not clean_q:
            return None

        # Strip conversational filler words: 'that', 'the', 'folder', 'folders', 'on here', 'in explorer', 'in file explorer', 'here'
        fillers = [
            r"\b(?:in\s+file\s+explorer|in\s+explorer)\b",
            r"\bon\s+here\b",
            r"\b(?:folder|folders|directory|dir)\b",
            r"\b(?:that|the|a|an)\b",
            r"\bhere\b",
        ]
        term = clean_q
        for f_pat in fillers:
            term = re.sub(f_pat, "", term, flags=re.IGNORECASE).strip()

        term = term.strip(" '\"`.,?!")
        term_lower = (term or clean_q).lower()

        # Plural/fuzzy normalization for system folders
        if term_lower in ["programs file", "program file", "program files", "programs files", "program files folder", "programs folder"]:
            return self.known_dirs["program files"]
        if term_lower in ["programs file (x86)", "program file (x86)", "program files (x86)", "programs files (x86)"]:
            return self.known_dirs["program files (x86)"]

        # 1. Check known directories
        for key, dir_path in self.known_dirs.items():
            if term_lower == key or term_lower.replace(" ", "") == key.replace(" ", ""):
                if os.path.isdir(dir_path):
                    return dir_path

        # 2. Check if query or cleaned term is an explicit existing path
        if os.path.exists(clean_q):
            if not folders_only or os.path.isdir(clean_q):
                return os.path.abspath(clean_q)
        if term and os.path.exists(term):
            if not folders_only or os.path.isdir(term):
                return os.path.abspath(term)

        # 3. Everything CLI (es.exe) if available
        if self.es_bin:
            try:
                cmd = [self.es_bin]
                if folders_only:
                    cmd.append("-ad")
                cmd.extend(["-n", "5", term_lower])
                res = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                    shell=False
                )
                if res.returncode == 0 and res.stdout:
                    for line in res.stdout.strip().splitlines():
                        candidate = line.strip()
                        if os.path.exists(candidate):
                            if not folders_only or os.path.isdir(candidate):
                                return candidate
            except Exception as e:
                print(f"[FileManager Everything Warning]: {e}")

        # 4. Bounded 2-level directory scan fallback
        search_roots = [
            self.known_dirs.get("desktop"),
            self.known_dirs.get("documents"),
            self.known_dirs.get("downloads"),
            self.known_dirs.get("program files"),
            PROJECT_ROOT
        ]

        target_token = term_lower
        target_condensed = term_lower.replace(" ", "").replace("_", "").replace("-", "")

        for root in search_roots:
            if not root or not os.path.isdir(root):
                continue

            # Check root itself
            base_name = os.path.basename(root).lower()
            base_condensed = base_name.replace(" ", "").replace("_", "").replace("-", "")
            if target_token == base_name or (target_condensed and target_condensed == base_condensed):
                return root

            # Level 1 and 2 search
            try:
                with os.scandir(root) as it1:
                    for entry1 in it1:
                        try:
                            if folders_only and not entry1.is_dir():
                                continue
                            e1_lower = entry1.name.lower()
                            e1_condensed = e1_lower.replace(" ", "").replace("_", "").replace("-", "")
                            if (
                                e1_lower == target_token
                                or (target_condensed and e1_condensed == target_condensed)
                                or (target_token and target_token in e1_lower)
                            ):
                                return os.path.abspath(entry1.path)

                            # Level 2 scan
                            if entry1.is_dir():
                                try:
                                    with os.scandir(entry1.path) as it2:
                                        for entry2 in it2:
                                            if folders_only and not entry2.is_dir():
                                                continue
                                            e2_lower = entry2.name.lower()
                                            e2_condensed = e2_lower.replace(" ", "").replace("_", "").replace("-", "")
                                            if (
                                                e2_lower == target_token
                                                or (target_condensed and e2_condensed == target_condensed)
                                                or (target_token and target_token in e2_lower)
                                            ):
                                                return os.path.abspath(entry2.path)
                                except (PermissionError, OSError):
                                    pass
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue

        return None

    def open_in_explorer(self, query: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Resolves query to a filesystem path and reveals it in Windows File Explorer.
        Handles pronoun references ("that folder", "the folder", "it", "this folder") using last_folder_path.
        """
        PRONOUN_REFERENCES = {
            "that folder", "the folder", "it", "this folder", "that", "folder",
            "last folder", "the created folder", "that created folder", "the new folder"
        }
        clean_norm = query.lower().strip().rstrip(".?!")
        clean_norm = re.sub(r"^(?:please\s+)?(?:open|reveal|show)\s+", "", clean_norm).strip()
        clean_norm = re.sub(r"\s+for\s+me$", "", clean_norm).strip()

        resolved_path = None
        if clean_norm in PRONOUN_REFERENCES or query.lower().strip() in PRONOUN_REFERENCES:
            if self.last_folder_path and (dry_run or os.path.exists(self.last_folder_path)):
                resolved_path = self.last_folder_path

        if not resolved_path:
            resolved_path = self.search_path(query, folders_only=True)
            if not resolved_path:
                resolved_path = self.search_path(query, folders_only=False)

        if not resolved_path:
            return {
                "status": "not_found",
                "path": None,
                "voice_response": f"I couldn't find the folder {query} on your system."
            }

        self.last_folder_path = resolved_path
        self.last_folder_name = os.path.basename(resolved_path) or resolved_path

        if not dry_run:
            try:
                subprocess.Popen(["explorer.exe", resolved_path], shell=False)
            except Exception as e:
                return {
                    "status": "error",
                    "path": resolved_path,
                    "voice_response": f"Failed to open {os.path.basename(resolved_path)} in File Explorer: {e}"
                }

        folder_name = os.path.basename(resolved_path) or resolved_path
        return {
            "status": "opened",
            "path": resolved_path,
            "voice_response": f"Opening {folder_name} in File Explorer."
        }

    def sanitize_folder_name(self, raw_name: str) -> str:
        """
        Strips path traversal elements (..) and illegal Windows characters (<>:"/\\|?*).
        """
        cleaned = raw_name.replace("..", "").replace("/", "").replace("\\", "")
        cleaned = re.sub(r'[<>:"/\\|?*]', "", cleaned).strip(" .")
        return cleaned or "New Folder"

    def create_folder(
        self,
        folder_name: str,
        parent_location: str = "desktop",
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Creates a new folder at the specified parent location with traversal protection.
        """
        clean_name = self.sanitize_folder_name(folder_name)

        # Resolve parent directory
        parent_dir = None
        if os.path.isdir(parent_location):
            parent_dir = os.path.abspath(parent_location)
        else:
            loc_lower = parent_location.lower().strip()
            if loc_lower in self.known_dirs:
                parent_dir = self.known_dirs[loc_lower]
            else:
                found = self.search_path(parent_location, folders_only=True)
                parent_dir = found or self.known_dirs.get("desktop", os.path.expanduser("~"))

        target_dir = os.path.abspath(os.path.join(parent_dir, clean_name))

        # Enforce that target_dir is strictly inside parent_dir (traversal defense)
        if not target_dir.startswith(parent_dir):
            target_dir = os.path.join(parent_dir, "Safe_Folder")

        self.last_folder_path = target_dir
        self.last_folder_name = clean_name

        if not dry_run:
            try:
                os.makedirs(target_dir, exist_ok=True)
            except Exception as e:
                return {
                    "status": "error",
                    "path": target_dir,
                    "voice_response": f"Failed to create folder {clean_name}: {e}"
                }

        parent_display = os.path.basename(parent_dir) or parent_location
        return {
            "status": "created",
            "path": target_dir,
            "voice_response": f"Created folder {clean_name} in {parent_display}."
        }

    def sanitize_file_name(self, raw_name: str, default_ext: str = ".py") -> str:
        """
        Sanitizes file name, strips illegal Windows characters (<>:"/\\|?*),
        and normalizes extension (e.g., .python -> .py).
        """
        cleaned = raw_name.replace("..", "").replace("/", "").replace("\\", "").strip(" '\"`")
        cleaned = re.sub(r'[<>:"/\\|?*]', "", cleaned).strip(" .")
        if cleaned.lower().endswith(".python"):
            cleaned = cleaned[:-7] + ".py"
        elif not os.path.splitext(cleaned)[1]:
            cleaned = f"{cleaned}{default_ext}"
        return cleaned or f"script{default_ext}"

    def create_file(
        self,
        file_name: str,
        content: str = "",
        location: str = "desktop",
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Creates a new file at location (default Desktop) with optional initial content.
        """
        clean_name = self.sanitize_file_name(file_name)
        parent_dir = None
        if os.path.isdir(location):
            parent_dir = os.path.abspath(location)
        else:
            loc_lower = location.lower().strip()
            parent_dir = self.known_dirs.get(loc_lower, self.get_real_desktop_path())

        target_file = os.path.abspath(os.path.join(parent_dir, clean_name))
        self.last_file_path = target_file
        self.last_file_name = clean_name

        if not content:
            if clean_name.endswith(".py"):
                content = f"# {clean_name} - Generated by Libra\nx = 10\nprint(f'x = {{x}}')\n"
            else:
                content = f"# {clean_name}\n"

        if not dry_run:
            try:
                os.makedirs(parent_dir, exist_ok=True)
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                return {
                    "status": "error",
                    "path": target_file,
                    "name": clean_name,
                    "voice_response": f"Failed to create file {clean_name}: {e}"
                }

        loc_label = os.path.basename(parent_dir) or "your system"
        return {
            "status": "created",
            "path": target_file,
            "name": clean_name,
            "content": content,
            "voice_response": f"Created {clean_name} on your {loc_label}."
        }

    def write_to_file(
        self,
        file_path_or_name: Optional[str] = None,
        content: str = "",
        mode: str = "append",
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Appends or overwrites content to a specified file or the last active file.
        """
        target = file_path_or_name or self.last_file_path
        if not target and self.last_file_path:
            target = self.last_file_path

        resolved_path = None
        if target:
            if os.path.isabs(target) and (dry_run or os.path.exists(target)):
                resolved_path = target
            else:
                resolved_path = self.search_path(target, folders_only=False)

        if not resolved_path:
            fallback_name = self.sanitize_file_name(target or "test.py")
            resolved_path = os.path.join(self.get_real_desktop_path(), fallback_name)

        self.last_file_path = resolved_path
        self.last_file_name = os.path.basename(resolved_path)

        if not dry_run:
            try:
                write_mode = "a" if mode == "append" else "w"
                with open(resolved_path, write_mode, encoding="utf-8") as f:
                    if mode == "append" and os.path.exists(resolved_path) and os.path.getsize(resolved_path) > 0:
                        f.write(f"\n{content}\n")
                    else:
                        f.write(f"{content}\n")
            except Exception as e:
                return {
                    "status": "error",
                    "path": resolved_path,
                    "name": self.last_file_name,
                    "voice_response": f"Failed to update {self.last_file_name}: {e}"
                }

        return {
            "status": "updated",
            "path": resolved_path,
            "name": self.last_file_name,
            "voice_response": f"Updated {self.last_file_name}."
        }

    def open_file(self, query: str = "", dry_run: bool = False) -> Dict[str, Any]:
        """
        Resolves query or pronoun reference to a file and opens it with the default system application (e.g. VS Code or Notepad).
        """
        PRONOUN_REFERENCES = {
            "that file", "the file", "it", "this file", "that", "the created file",
            "that created file", "the new file", "my file", "the python file", "that python file"
        }
        clean_norm = query.lower().strip().rstrip(".?!")
        clean_norm = re.sub(r"^(?:please\s+)?(?:open|reveal|show|view|edit)\s+", "", clean_norm).strip()
        clean_norm = re.sub(r"\s+for\s+me(?:\s+to\s+see)?$", "", clean_norm).strip()
        clean_norm = re.sub(r"\s+that\s+you\s+(?:just\s+)?created(?:\s+not\s+long\s+ago)?$", "", clean_norm).strip()

        resolved_path = None
        if not clean_norm or clean_norm in PRONOUN_REFERENCES or query.lower().strip() in PRONOUN_REFERENCES:
            if self.last_file_path and (dry_run or os.path.exists(self.last_file_path)):
                resolved_path = self.last_file_path

        if not resolved_path:
            target_search = clean_norm or query
            resolved_path = self.search_path(target_search, folders_only=False)
            if not resolved_path and not os.path.splitext(target_search)[1]:
                resolved_path = self.search_path(f"{target_search}.py", folders_only=False)
                if not resolved_path:
                    resolved_path = self.search_path(f"{target_search}.txt", folders_only=False)

        if not resolved_path and self.last_file_path:
            resolved_path = self.last_file_path

        if not resolved_path:
            return {
                "status": "not_found",
                "path": None,
                "voice_response": f"I couldn't find the file {query} on your system."
            }

        self.last_file_path = resolved_path
        self.last_file_name = os.path.basename(resolved_path)

        if not dry_run:
            try:
                os.startfile(resolved_path)
            except Exception:
                code_bin = shutil.which("code")
                if code_bin:
                    subprocess.Popen([code_bin, resolved_path], shell=True)
                else:
                    subprocess.Popen(["notepad.exe", resolved_path], shell=False)

        file_display = os.path.basename(resolved_path)
        return {
            "status": "opened",
            "path": resolved_path,
            "name": file_display,
            "voice_response": f"Opening {file_display}."
        }
