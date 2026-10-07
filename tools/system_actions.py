import os
import glob
import subprocess
import webbrowser
import urllib.parse

def get_installed_shortcuts():
    """Scans Windows Start Menu directories for all installed application shortcuts."""
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
                # Exclude uninstaller shortcuts
                if "uninstall" not in clean_name and "help" not in clean_name:
                    apps[clean_name] = path
    return apps

def launch_any_application(target_name: str) -> tuple[bool, str]:
    """Dynamically finds and launches any installed Windows application or game."""
    target = target_name.lower().strip()
    
    # 1. Direct system shortcuts scan
    installed_apps = get_installed_shortcuts()
    for app_name, path in installed_apps.items():
        if target in app_name or app_name in target:
            try:
                os.startfile(path)
                return True, f"Launching {app_name.title()}."
            except Exception as e:
                print(f"[Launch Error]: {e}")

    # 2. Known common launchers fallback paths
    common_roots = [
        os.path.expandvars(r"%LOCALAPPDATA%"),
        os.path.expandvars(r"%PROGRAMFILES%"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%"),
        r"C:\Riot Games",
    ]
    for root in common_roots:
        if os.path.exists(root):
            matches = glob.glob(f"{root}/**/{target}*.exe", recursive=True)
            if matches:
                try:
                    subprocess.Popen(matches[0], shell=True)
                    return True, f"Launching {target.title()}."
                except Exception as e:
                    print(f"[Executable Launch Error]: {e}")

    # 3. Direct Windows Shell execute (calc, notepad, cmd, or URI protocol like spotify:)
    try:
        os.system(f"start {target}")
        return True, f"Attempting to launch {target.title()}."
    except Exception:
        pass

    return False, f"I could not locate an application named {target_name} on your system."

def web_search(query: str, platform: str = "google") -> str:
    """Performs web searches or opens queries across platforms."""
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
    if not url.startswith("http"):
        url = f"https://{url}"
    webbrowser.open(url)
    return f"Opening {url}."