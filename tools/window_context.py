import os
import re
import sys
import ctypes
from ctypes import wintypes
from typing import Dict, Any, Optional, List

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


APP_FRIENDLY_NAMES = {
    "code.exe": ("VS Code", "ide"),
    "cursor.exe": ("Cursor IDE", "ide"),
    "pycharm64.exe": ("PyCharm", "ide"),
    "devenv.exe": ("Visual Studio", "ide"),
    "sublime_text.exe": ("Sublime Text", "ide"),
    "notepad++.exe": ("Notepad++", "ide"),
    "notepad.exe": ("Notepad", "document"),
    "winword.exe": ("Microsoft Word", "document"),
    "excel.exe": ("Microsoft Excel", "document"),
    "powerpnt.exe": ("PowerPoint", "document"),
    "windowsterminal.exe": ("Windows Terminal", "terminal"),
    "powershell.exe": ("PowerShell", "terminal"),
    "pwsh.exe": ("PowerShell", "terminal"),
    "cmd.exe": ("Command Prompt", "terminal"),
    "chrome.exe": ("Google Chrome", "browser"),
    "msedge.exe": ("Microsoft Edge", "browser"),
    "firefox.exe": ("Mozilla Firefox", "browser"),
    "brave.exe": ("Brave Browser", "browser"),
    "opera.exe": ("Opera Browser", "browser"),
    "spotify.exe": ("Spotify", "media"),
    "vlc.exe": ("VLC Media Player", "media"),
    "discord.exe": ("Discord", "communication"),
    "telegram.exe": ("Telegram", "communication"),
    "whatsapp.exe": ("WhatsApp", "communication"),
    "blender.exe": ("Blender", "creative"),
    "robloxplayerbeta.exe": ("Roblox", "game"),
    "steam.exe": ("Steam", "game"),
    "explorer.exe": ("File Explorer", "system"),
}


class ActiveWindowEngine:
    """
    Active-Window Context Awareness Engine (v10.0).
    Uses Win32 user32 + psutil to identify the foreground application, active file,
    browser tab, or running terminal in <2ms, enabling zero-friction contextual voice queries:
      - 'What am I working on?' / 'What window am I in?'
      - 'What does this error mean?' / 'Explain what this script does'
      - 'Summarize what's on this page' / 'Write a reply to this thread'
    """

    def __init__(self):
        self.mock_window_info: Optional[Dict[str, Any]] = None
        self.last_window_snapshot: Optional[Dict[str, Any]] = None

    def set_mock_window(self, mock_info: Optional[Dict[str, Any]]):
        """Allows unit tests to simulate specific foreground windows deterministically."""
        self.mock_window_info = mock_info

    def get_active_window_info(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Inspects the currently focused foreground window on Windows 11.
        Extracts process name, friendly app label, category, window title,
        and parses active IDE filenames or browser tab titles.
        """
        if self.mock_window_info is not None:
            info = dict(self.mock_window_info)
            self._enrich_parsed_metadata(info)
            self.last_window_snapshot = info
            return info

    @staticmethod
    def _find_top_external_window(user32, current_hwnd: int, current_pid: int) -> Optional[int]:
        """
        Finds the topmost visible application window in Z-order that is not the Libra GUI process.
        Ensures Libra inspects the user's actual workspace (e.g. VS Code, Chrome) instead of her own interface.
        """
        class TargetHolder:
            found_hwnd = None

        ignored_titles = {
            "program manager", "settings", "default ime", "msctfime ui",
            "windows input experience", "taskbar", "search", "cortana",
            "action center", "snap assist", ""
        }

        def enum_cb(h, lparam):
            if h == current_hwnd or not user32.IsWindowVisible(h):
                return True
            length = user32.GetWindowTextLengthW(h)
            if length <= 0:
                return True
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(h, buff, length + 1)
            t = buff.value.strip()
            if not t or t.lower() in ignored_titles or "LIBRA // CYBERNETIC" in t.upper():
                return True

            w_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(w_pid))
            if w_pid.value == current_pid or w_pid.value == os.getpid():
                return True

            if user32.IsIconic(h):
                return True

            TargetHolder.found_hwnd = h
            return False

        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        try:
            user32.EnumWindows(EnumWindowsProc(enum_cb), 0)
        except Exception:
            pass

        return TargetHolder.found_hwnd

    def get_active_window_info(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Inspects the currently focused foreground window on Windows 11.
        Extracts process name, friendly app label, category, window title,
        and parses active IDE filenames or browser tab titles.
        If the focused window is Libra herself, resolves the topmost external work window.
        """
        if self.mock_window_info is not None:
            info = dict(self.mock_window_info)
            self._enrich_parsed_metadata(info)
            self.last_window_snapshot = info
            return info

        info: Dict[str, Any] = {
            "hwnd": 0,
            "pid": 0,
            "process_name": "Unknown",
            "app_label": "Desktop",
            "app_category": "general",
            "window_title": "",
            "active_file": None,
            "active_file_path": None,
            "project_name": None,
            "page_title": None,
            "memory_mb": 0.0,
        }

        if sys.platform != "win32" or not hasattr(ctypes, "windll"):
            self.last_window_snapshot = info
            return info

        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                self.last_window_snapshot = info
                return info

            # Check if foreground window is Libra herself
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()

            if pid.value == os.getpid() or "LIBRA // CYBERNETIC" in title.upper():
                external_hwnd = self._find_top_external_window(user32, hwnd, pid.value)
                if external_hwnd:
                    hwnd = external_hwnd
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value.strip()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            info["hwnd"] = int(hwnd)
            info["window_title"] = title
            info["pid"] = int(pid.value)

            if info["pid"] > 0 and PSUTIL_AVAILABLE:
                try:
                    proc = psutil.Process(info["pid"])
                    proc_name = proc.name()
                    info["process_name"] = proc_name
                    mem_bytes = proc.memory_info().rss
                    info["memory_mb"] = round(mem_bytes / (1024 * 1024), 1)

                    proc_lower = proc_name.lower()
                    if proc_lower in APP_FRIENDLY_NAMES:
                        info["app_label"], info["app_category"] = APP_FRIENDLY_NAMES[proc_lower]
                    else:
                        info["app_label"] = os.path.splitext(proc_name)[0].replace("_", " ").title()
                except Exception:
                    pass
        except Exception as e:
            print(f"[ActiveWindowEngine Inspection Warning]: {e}")

        self._enrich_parsed_metadata(info)
        self.last_window_snapshot = info
        return info

    def _enrich_parsed_metadata(self, info: Dict[str, Any]):
        """Parses IDE active file/project or Browser tab title from window_title."""
        title = (info.get("window_title") or "").strip()
        proc_lower = (info.get("process_name") or "").lower()

        if proc_lower in APP_FRIENDLY_NAMES and info.get("app_category", "general") == "general":
            info["app_label"], info["app_category"] = APP_FRIENDLY_NAMES[proc_lower]

        category = info.get("app_category", "general")

        # Also infer category from window title if process name wasn't matched
        title_lower = title.lower()
        if category == "general":
            if "visual studio code" in title_lower or "cursor" in title_lower or "pycharm" in title_lower:
                category = "ide"
                info["app_category"] = "ide"
                if "visual studio code" in title_lower:
                    info["app_label"] = "VS Code"
            elif any(b in title_lower for b in ["google chrome", "microsoft edge", "mozilla firefox", "brave"]):
                category = "browser"
                info["app_category"] = "browser"
                if "google chrome" in title_lower:
                    info["app_label"] = "Google Chrome"
                elif "microsoft edge" in title_lower:
                    info["app_label"] = "Microsoft Edge"
            elif any(t in title_lower for t in ["powershell", "command prompt", "windows terminal"]):
                category = "terminal"
                info["app_category"] = "terminal"
                info["app_label"] = "Terminal"

        # 1. IDE Title Parsing: e.g., "● llm.py - LibraAi - Visual Studio Code"
        if category == "ide" and title:
            parts = [p.strip(" ●*•") for p in re.split(r"\s+[-—]\s+", title) if p.strip()]
            if len(parts) >= 2:
                candidate_file = parts[0]
                if "." in candidate_file or candidate_file.endswith((".py", ".js", ".ts", ".html", ".css", ".md", ".json", ".cpp", ".rs")):
                    info["active_file"] = candidate_file
                    if len(parts) >= 3:
                        info["project_name"] = parts[1]
                    info["active_file_path"] = self._resolve_file_on_disk(candidate_file)

        # 2. Browser Title Parsing: e.g., "Pull Request #42 · GitHub - Google Chrome"
        elif category == "browser" and title:
            cleaned_tab = re.sub(
                r"\s*[-—]\s*(?:Google Chrome|Microsoft​?\s*Edge|Mozilla Firefox|Brave|Opera).*$",
                "",
                title,
                flags=re.IGNORECASE,
            ).strip()
            # Also strip Edge's "and X more pages - Personal"
            cleaned_tab = re.sub(r"\s+and\s+\d+\s+more\s+pages?.*$", "", cleaned_tab, flags=re.IGNORECASE).strip()
            info["page_title"] = cleaned_tab or title

    def _resolve_file_on_disk(self, filename: str) -> Optional[str]:
        """Attempts to locate an active IDE filename inside PROJECT_ROOT."""
        if not filename:
            return None
        clean_f = filename.strip(" ●*•")
        if os.path.isabs(clean_f) and os.path.isfile(clean_f):
            return clean_f

        # Check direct relative path or search inside PROJECT_ROOT
        direct = os.path.join(PROJECT_ROOT, clean_f)
        if os.path.isfile(direct):
            return direct

        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in {"venv", ".git", "__pycache__", "node_modules", ".idea"}]
            for f in files:
                if f.lower() == clean_f.lower():
                    return os.path.join(root, f)
        return None

    def summarize_active_window(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Answers 'What am I working on?', 'What window am I in?', or 'What app is focused?'.
        """
        info = self.get_active_window_info(dry_run=dry_run)
        app = info.get("app_label") or "Desktop"
        cat = info.get("app_category", "general")
        title = info.get("window_title") or ""
        active_file = info.get("active_file")
        project = info.get("project_name")
        page = info.get("page_title")
        mem = info.get("memory_mb", 0.0)

        if cat == "ide" and active_file:
            proj_clause = f" in the {project} project" if project else ""
            voice = f"You're currently in {app} working on {active_file}{proj_clause}."
        elif cat == "browser" and page:
            voice = f"You have {app} focused on {page}."
        elif cat == "terminal":
            voice = f"You're in {app}" + (f" ({title})." if title and title.lower() != app.lower() else ".")
        elif title:
            voice = f"You're currently focused on {app} — {title}."
        else:
            voice = f"You currently have {app} in focus."

        if mem and mem > 50:
            voice = f"{voice[:-1]}, using {int(mem)} megabytes of RAM."

        return {
            "status": "success",
            "action": "active_window",
            "sub_action": "status",
            "window_info": info,
            "voice_response": voice,
        }

    def handle_contextual_query(
        self,
        prompt: str,
        clipboard_agent: Optional[Any] = None,
        model_mgr: Optional[Any] = None,
        llm_callback: Optional[Any] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Handles context-dependent queries based on the foreground application:
          1. 'What am I working on?' / 'What window is active?'
          2. In VS Code / Terminal: 'What does this error mean?' / 'Explain what this script does'
          3. In Browser: 'Summarize what's on this page' / 'Write a reply to this thread'
        """
        q_low = (prompt or "").lower().strip()
        info = self.get_active_window_info(dry_run=dry_run)
        app_label = info.get("app_label", "Desktop")
        category = info.get("app_category", "general")
        active_file = info.get("active_file")
        active_file_path = info.get("active_file_path")
        page_title = info.get("page_title") or info.get("window_title") or "the current page"

        # 1. Direct "What am I working on?" / "What window am I in?"
        if re.search(
            r"\b(?:what\s+(?:am\s+i|a\s+man|i'm|i\s+am)\s+(?:working|walking|workin)\s+on|what\s+am\s+i\s+(?:doing|looking\s+at)|what\s+(?:window|app|application)\s+(?:am\s+i\s+in|is\s+(?:active|focused|open))|which\s+window\s+is\s+active)\b",
            q_low,
        ):
            return self.summarize_active_window(dry_run=dry_run)

        # 2. Error / Bug Diagnosis in Active Window ("What does this error mean?", "How do I fix this bug?")
        if re.search(
            r"\b(?:what\s+does\s+this\s+(?:error|exception|warning|traceback)\s+mean|explain\s+this\s+(?:error|bug|traceback)|how\s+(?:do\s+i\s+|to\s+)?fix\s+this\s+(?:error|bug|issue))\b",
            q_low,
        ):
            clip_text = clipboard_agent.get_clipboard_text() if clipboard_agent else ""
            if clip_text and len(clip_text.strip()) > 5:
                diag = clipboard_agent.explain_clipboard(
                    llm_callback=llm_callback,
                    text=clip_text,
                    dry_run=dry_run,
                )
                voice = f"In {app_label}: {diag.get('voice_response', 'Checked your clipboard error.')}"
                return {
                    "status": "success",
                    "action": "active_window",
                    "sub_action": "explain_error",
                    "window_info": info,
                    "source": "clipboard",
                    "voice_response": voice,
                }

            # Fallback to screen vision if no clipboard text
            if model_mgr and not dry_run:
                vis_res = model_mgr.analyze_screen(
                    f"Read and explain the error message visible in {app_label} in 2 concise sentences.",
                    active_window_only=True,
                    dry_run=False,
                )
                return {
                    "status": "success",
                    "action": "active_window",
                    "sub_action": "explain_error",
                    "window_info": info,
                    "source": "screen_vision",
                    "voice_response": vis_res.get("voice_response", f"Analyzed {app_label} window for errors."),
                }

            target_desc = f"{active_file} in {app_label}" if active_file else app_label
            return {
                "status": "success",
                "action": "active_window",
                "sub_action": "explain_error",
                "window_info": info,
                "source": "window_context",
                "voice_response": f"I checked {target_desc}. Copy the traceback or error line to your clipboard and I'll pinpoint the exact fix.",
            }

        # 3. Script / Code Explanation ("Explain what this script does", "What does this file do?")
        if re.search(
            r"\b(?:explain\s+what\s+this\s+(?:script|file|code|module|function)\s+does|what\s+does\s+this\s+(?:script|file|code|module|function)\s+do|summarize\s+this\s+(?:script|file|code))\b",
            q_low,
        ):
            code_snippet = ""
            source_name = active_file or app_label
            if active_file_path and os.path.isfile(active_file_path):
                try:
                    with open(active_file_path, "r", encoding="utf-8", errors="ignore") as f:
                        code_snippet = f.read(2500)
                except Exception:
                    pass

            if not code_snippet and clipboard_agent:
                clip_candidate = clipboard_agent.get_clipboard_text()
                if clip_candidate and len(clip_candidate) > 15:
                    code_snippet = clip_candidate[:2500]
                    source_name = "your copied code"

            if code_snippet:
                if dry_run or llm_callback is None:
                    lines_count = len(code_snippet.splitlines())
                    voice = f"You're viewing {source_name} in {app_label} ({lines_count} lines). It defines core logic and helper functions for this module."
                else:
                    sys_p = (
                        f"You are Libra, analyzing {source_name} open in {app_label}. "
                        "Explain what this script or code does in 2 crisp, natural spoken sentences. No markdown."
                    )
                    if hasattr(llm_callback, "call_ollama"):
                        voice = llm_callback.call_ollama("qwen3:8b", f"Code:\n{code_snippet}", system_prompt=sys_p, timeout=25)
                    elif callable(llm_callback):
                        voice = llm_callback(f"{sys_p}\n\nCode:\n{code_snippet}")
                    else:
                        voice = ""
                    if not voice:
                        voice = f"{source_name} in {app_label} implements core module functionality."

                return {
                    "status": "success",
                    "action": "active_window",
                    "sub_action": "explain_script",
                    "window_info": info,
                    "active_file": active_file,
                    "voice_response": voice,
                }

            return {
                "status": "success",
                "action": "active_window",
                "sub_action": "explain_script",
                "window_info": info,
                "voice_response": f"You're in {app_label}" + (f" viewing {active_file}." if active_file else ". Highlight and copy any code block if you want a line-by-line breakdown."),
            }

        # 4. Browser / Thread Reply Generation ("Can you write a reply to this thread?", "Draft a reply to this")
        if re.search(
            r"\b(?:write\s+a\s+reply|draft\s+a\s+reply|reply\s+to\s+this\s+(?:thread|post|email|message|comment)|help\s+me\s+reply\s+to\s+this)\b",
            q_low,
        ):
            clip_context = clipboard_agent.get_clipboard_text() if clipboard_agent else ""
            context_desc = f"Page/Thread: {page_title}\n"
            if clip_context:
                context_desc += f"Copied Thread Text: {clip_context[:1000]}"

            if dry_run or llm_callback is None:
                draft = f"Thanks for the update on {page_title}! I've reviewed the details and everything looks good to proceed."
                voice = f"I drafted a reply for {page_title} in {app_label} and copied it to your clipboard so you can paste it right in."
            else:
                sys_p = (
                    "Write a smart, natural, concise reply to the user's active thread or message. "
                    "Return ONLY the reply text ready to be pasted. No quotes or intro."
                )
                if hasattr(llm_callback, "call_ollama"):
                    draft = llm_callback.call_ollama("qwen3:8b", context_desc, system_prompt=sys_p, timeout=25)
                elif callable(llm_callback):
                    draft = llm_callback(f"{sys_p}\n\n{context_desc}")
                else:
                    draft = ""
                draft = (draft or f"Thanks for sharing this! Looking at {page_title}, that makes sense to me.").strip()
                voice = f"I've copied a reply draft to your clipboard for {page_title}: {draft}"

            if clipboard_agent and not dry_run:
                clipboard_agent.set_clipboard(draft)

            return {
                "status": "success",
                "action": "active_window",
                "sub_action": "draft_reply",
                "window_info": info,
                "draft": draft,
                "voice_response": voice,
            }

        # 5. Browser / Page Summarization ("Summarize what's on this page", "Summarize this page/article")
        if re.search(
            r"\b(?:summarize\s+(?:what(?:'s|\s+is)\s+on\s+)?this\s+(?:page|article|tab|website|site|window)|what(?:'s|\s+is)\s+this\s+(?:page|article|tab)\s+about)\b",
            q_low,
        ):
            clip_context = clipboard_agent.get_clipboard_text() if clipboard_agent else ""
            if dry_run:
                voice = f"You're viewing {page_title} in {app_label}. Summarized key points from the active page."
                return {
                    "status": "success",
                    "action": "active_window",
                    "sub_action": "summarize_page",
                    "window_info": info,
                    "page_title": page_title,
                    "voice_response": voice,
                }

            if clip_context and len(clip_context) > 60 and llm_callback:
                sys_p = f"Summarize this content from '{page_title}' in 2 concise spoken sentences. No markdown."
                if hasattr(llm_callback, "call_ollama"):
                    voice = llm_callback.call_ollama("qwen3:8b", clip_context[:2000], system_prompt=sys_p, timeout=25)
                elif callable(llm_callback):
                    voice = llm_callback(f"{sys_p}\n\n{clip_context[:2000]}")
                else:
                    voice = ""
                if voice:
                    return {
                        "status": "success",
                        "action": "active_window",
                        "sub_action": "summarize_page",
                        "window_info": info,
                        "page_title": page_title,
                        "voice_response": voice,
                    }

            if model_mgr:
                vis_res = model_mgr.analyze_screen(
                    f"Summarize the main content visible on '{page_title}' in {app_label} in 2 spoken sentences.",
                    active_window_only=True,
                    dry_run=False,
                )
                return {
                    "status": "success",
                    "action": "active_window",
                    "sub_action": "summarize_page",
                    "window_info": info,
                    "page_title": page_title,
                    "voice_response": vis_res.get("voice_response", f"You are viewing {page_title} in {app_label}."),
                }

            return {
                "status": "success",
                "action": "active_window",
                "sub_action": "summarize_page",
                "window_info": info,
                "page_title": page_title,
                "voice_response": f"You're viewing {page_title} in {app_label}.",
            }

        return self.summarize_active_window(dry_run=dry_run)
