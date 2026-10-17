import os
import glob
import subprocess
import webbrowser
import urllib.parse

from core.dispatcher import SafeOSDispatcher

_DISPATCHER_INSTANCE = None


def _get_dispatcher() -> SafeOSDispatcher:
    global _DISPATCHER_INSTANCE
    if _DISPATCHER_INSTANCE is None:
        _DISPATCHER_INSTANCE = SafeOSDispatcher()
    return _DISPATCHER_INSTANCE


def get_installed_shortcuts():
    """Scans Windows Start Menu directories for installed application shortcuts."""
    shortcut_dirs = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"),
    ]

    apps = {}
    for base in shortcut_dirs:
        if os.path.exists(base):
            for path in glob.glob(f"{base}/**/*.lnk", recursive=True):
                filename = os.path.basename(path).lower()
                clean_name = filename.replace(".lnk", "").strip()
                if "uninstall" not in clean_name and "help" not in clean_name:
                    apps[clean_name] = path
    return apps


def launch_any_application(target_name: str, dry_run: bool = False) -> tuple[bool, str]:
    """
    Dynamically finds and launches any installed Windows application or game
    via SafeOSDispatcher and GameDiscoveryEngine (never emitting bare roblox-player:
    or ms-windows-store: popups).
    """
    disp = _get_dispatcher()
    ok, msg = disp.launch_app(target_name, dry_run=dry_run)
    if ok:
        return ok, msg

    target = target_name.lower().strip()
    built_in_tools = ["notepad", "calc", "calculator", "explorer", "taskmgr"]
    if target in built_in_tools:
        if dry_run:
            return True, f"Launching {target.title()}."
        try:
            subprocess.Popen([target], close_fds=True)
            return True, f"Launching {target.title()}."
        except Exception as e:
            return False, f"Failed to launch {target}: {e}"

    return ok, msg


def close_any_application(target_name: str, dry_run: bool = False) -> tuple[bool, str]:
    """Safely terminates a named user application via SafeOSDispatcher."""
    disp = _get_dispatcher()
    return disp.close_app(target_name, dry_run=dry_run)


def find_and_open_file(target_file: str) -> tuple[bool, str]:
    """Searches common user directories and opens matching files."""
    search_dirs = [
        os.path.expanduser("~/Desktop"),
        os.path.expanduser("~/OneDrive/Desktop"),
        os.path.expanduser("~/Documents"),
        os.path.expanduser("~/Downloads"),
    ]
    target_clean = target_file.lower().strip()

    for base in search_dirs:
        if os.path.exists(base):
            for root, _, files in os.walk(base):
                for file in files:
                    if target_clean in file.lower():
                        full_path = os.path.join(root, file)
                        try:
                            subprocess.Popen(["explorer.exe", full_path], close_fds=True)
                            return True, f"Opening {file}."
                        except Exception as e:
                            return False, f"Error opening file: {e}"

    return False, f"Could not find {target_file} in your user directories."


def web_search(query: str, platform: str = "google") -> str:
    """Performs web searches or opens queries across platforms in the browser."""
    encoded = urllib.parse.quote_plus(query.strip())
    if platform.lower() == "youtube":
        url = f"https://www.youtube.com/results?search_query={encoded}"
        webbrowser.open(url)
        return f"Searching YouTube for {query}."
    else:
        url = f"https://www.google.com/search?q={encoded}"
        webbrowser.open(url)
        return f"Searching Google for {query}."


def open_url(url: str) -> str:
    """Navigates the default web browser to the given URL."""
    if not url.startswith("http"):
        url = f"https://{url}"
    webbrowser.open(url)
    return f"Opening {url}."