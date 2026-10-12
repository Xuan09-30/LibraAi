import os
import glob
import subprocess
import webbrowser
import urllib.parse


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


def launch_any_application(target_name: str) -> tuple[bool, str]:
    """Dynamically finds and launches any installed Windows application or game."""
    target = target_name.lower().strip()

    # 1. Direct Game/App Protocol URI Handlers (Bypasses shortcut scanning entirely)
    protocol_map = {
        "roblox": "roblox-player:",
        "roblox player": "roblox-player:",
        "spotify": "spotify:",
        "steam": "steam:",
        "discord": "discord:",
    }

    if target in protocol_map:
        try:
            subprocess.Popen(f'start "" "{protocol_map[target]}"', shell=True)
            return True, f"Launching {target.title()}."
        except Exception as e:
            print(f"[Protocol Launch Failed]: {e}")

    # 2. Check Start Menu Shortcuts (.lnk)
    installed_apps = get_installed_shortcuts()
    for app_name, path in installed_apps.items():
        if target in app_name or app_name in target:
            try:
                subprocess.Popen(f'start "" "{path}"', shell=True)
                return True, f"Launching {app_name.title()}."
            except Exception as e:
                print(f"[Shell Start Error]: {e}")
                try:
                    os.startfile(path)
                    return True, f"Launching {app_name.title()}."
                except Exception as ex:
                    print(f"[Fallback startfile Error]: {ex}")

    # 3. Known Common Launcher Folders and Executable Locations
    common_roots = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
        os.path.expandvars(r"%LOCALAPPDATA%"),
        os.path.expandvars(r"%APPDATA%"),
        os.path.expandvars(r"%PROGRAMFILES%"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%"),
        r"C:\Riot Games",
    ]
    for root in common_roots:
        if os.path.exists(root):
            matches = glob.glob(f"{root}/**/{target}*.exe", recursive=True)
            if matches:
                try:
                    subprocess.Popen(f'start "" "{matches[0]}"', shell=True)
                    return True, f"Launching {target.title()}."
                except Exception as e:
                    print(f"[Executable Launch Error]: {e}")

    # 4. Built-in Windows Utilities & Commands (calc, notepad, cmd)
    built_in_tools = ["notepad", "calc", "calculator", "cmd", "explorer", "taskmgr", "regedit"]
    if target in built_in_tools:
        try:
            subprocess.Popen(f'start "" "{target}"', shell=True)
            return True, f"Launching {target.title()}."
        except Exception as e:
            print(f"[Built-in Launch Error]: {e}")

    return False, f"I could not locate an application named {target_name.title()} on your system."


def close_any_application(target_name: str) -> tuple[bool, str]:
    """Forcefully terminates an application process matching the target name."""
    clean_target = target_name.lower().replace(".exe", "").strip()

    aliases = {
        "spotify": "Spotify.exe",
        "valorant": "VALORANT.exe",
        "roblox": "RobloxPlayerBeta.exe",
        "roblox player": "RobloxPlayerBeta.exe",
        "modrinth": "Modrinth App.exe",
        "modrinth app": "Modrinth App.exe",
        "riot client": "RiotClientServices.exe",
        "discord": "Discord.exe",
        "chrome": "chrome.exe",
        "steam": "steam.exe",
        "notepad": "notepad.exe",
        "calculator": "CalculatorApp.exe",
    }

    proc_name = aliases.get(clean_target, f"{clean_target}.exe")

    try:
        res = subprocess.run(["taskkill", "/F", "/IM", proc_name, "/T"], capture_output=True, text=True)
        if res.returncode == 0:
            return True, f"Closed {target_name.title()}."
        return False, f"I could not locate an active process for {target_name.title()}."
    except Exception as e:
        return False, f"Failed to close {target_name}: {e}"


def find_and_open_file(target_file: str) -> tuple[bool, str]:
    """Searches common user directories and opens matching files."""
    search_dirs = [
        os.path.expanduser("~/Desktop"),
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
                            subprocess.Popen(f'start "" "{full_path}"', shell=True)
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