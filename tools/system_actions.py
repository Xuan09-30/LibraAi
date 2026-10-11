import os
import glob
import subprocess
import webbrowser
import urllib.parse
import difflib
import shutil

def get_installed_shortcuts():
    """
    Scans Windows Start Menu AND User/Public Desktops for all installed
    shortcuts (.lnk and .url Steam/Epic shortcuts).
    """
    shortcut_dirs = [
        # User & Public Start Menus
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"),
        # User & Public Desktops (Catches games and desktop launchers)
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
        os.path.expandvars(r"%PUBLIC%\Desktop"),
    ]
    
    apps = {}
    for base in shortcut_dirs:
        if os.path.exists(base):
            for path in glob.glob(f"{base}/**/*.*", recursive=True):
                ext = os.path.splitext(path)[1].lower()
                if ext in [".lnk", ".url"]:
                    filename = os.path.basename(path).lower()
                    clean_name = filename.replace(".lnk", "").replace(".url", "").strip()
                    if "uninstall" not in clean_name and "help" not in clean_name:
                        apps[clean_name] = path
    return apps

def launch_any_application(target_name: str) -> tuple[bool, str]:
    """
    Dynamically finds and launches any installed Windows application, 
    custom launcher, Steam/Riot game, or developer environment.
    """
    target = target_name.lower().strip()
    
    # 1. Direct protocol & custom alias dictionary
    direct_protocol_map = {
        "spotify": "cmd /c start spotify:",
        "discord": "cmd /c start discord:",
        "steam": "cmd /c start steam:",
        "epic": "cmd /c start com.epicgames.launcher:",
        "epic games": "cmd /c start com.epicgames.launcher:",
        "riot": "cmd /c start riotclient:",
        "riot client": "cmd /c start riotclient:",
        "valorant": "cmd /c start riotclient: --launch-product=valorant --launch-patchline=live",
        "league of legends": "cmd /c start riotclient: --launch-product=league_of_legends --launch-patchline=live",
        "lol": "cmd /c start riotclient: --launch-product=league_of_legends --launch-patchline=live",
        "vscode": "code",
        "vs code": "code",
        "visual studio code": "code",
        "terminal": "wt.exe",
        "cmd": "cmd.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "notepad": "notepad.exe"
    }

    if target in direct_protocol_map:
        try:
            subprocess.Popen(direct_protocol_map[target], shell=True)
            return True, f"Launching {target.title()}."
        except Exception as e:
            print(f"[Protocol Launch Error]: {e}")

    # 2. Desktop & Start Menu Shortcuts Scan (.lnk and .url)
    installed_apps = get_installed_shortcuts()
    
    # Exact or substring match
    for app_name, path in installed_apps.items():
        if target == app_name or target in app_name or app_name in target:
            try:
                os.startfile(path)
                return True, f"Launching {app_name.title()}."
            except Exception as e:
                print(f"[Shortcut Launch Error]: {e}")

    # 3. Scan Common Executable Roots (Local programs, Games, Riot, etc.)
    common_roots = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
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

    # 4. Fallback: Windows Shell Execution
    try:
        os.system(f"start {target}")
        return True, f"Attempting to launch {target.title()}."
    except Exception:
        pass

    return False, f"I could not locate an application or game named {target_name} on your system."

def web_search(query: str, platform: str = "google") -> str:
    """Performs web searches across platforms."""
    encoded = urllib.parse.quote_plus(query.strip())
    if platform.lower() == "youtube":
        url = f"https://www.youtube.com/results?search_query={encoded}"
        webbrowser.open(url)
        return f"Searching YouTube for {query}."
    else:
        url = f"https://www.google.com/search?q={encoded}"
        webbrowser.open(url)
        return f"Searching Google for {query}."

def find_and_open_file(target_query: str) -> tuple[bool, str]:
    """
    Locates and opens any file across user drives using:
    1. Everything CLI (instant NTFS search across entire PC if installed)
    2. Deep targeted walk across Documents, Downloads, Workspaces, and Videos
    """
    query = target_query.lower().strip()
    
    # -------------------------------------------------------------
    # METHOD 1: Instant Whole-Drive NTFS Index Search (Everything CLI)
    # -------------------------------------------------------------
    es_path = shutil.which("es.exe") or shutil.which("es")
    if es_path:
        try:
            # Query the Everything search database instantly
            cmd = f'"{es_path}" -n 1 -sort-dm "{query}"'
            result = subprocess.check_output(cmd, shell=True, text=True, errors="ignore").strip()
            if result and os.path.exists(result):
                os.startfile(result)
                filename = os.path.basename(result)
                return True, f"Opening {filename}."
        except Exception as e:
            print(f"[ES Search Error]: {e}")

    # -------------------------------------------------------------
    # METHOD 2: Targeted Multi-Directory Crawl
    # -------------------------------------------------------------
    search_roots = [
        os.path.expandvars(r"%USERPROFILE%\Downloads"),
        os.path.expandvars(r"%USERPROFILE%\Documents"),
        os.path.expandvars(r"%USERPROFILE%\Pictures"),
        os.path.expandvars(r"%USERPROFILE%\Videos"),
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
        r"C:\Users\User\Desktop\The Ultimate Project",  # Project workspaces
    ]

    # Ignore heavy runtime/cache folders to maintain high speed
    ignored_folders = {
        ".git", "node_modules", "venv", "__pycache__", "cache", 
        "site-packages", "appdata", "build", "dist"
    }

    candidates = []

    for root_dir in search_roots:
        if not os.path.exists(root_dir):
            continue
            
        for root, dirs, files in os.walk(root_dir):
            # Prune ignored folders in-place
            dirs[:] = [d for d in dirs if d.lower() not in ignored_folders and not d.startswith(".")]

            for file in files:
                file_lower = file.lower()
                clean_name = os.path.splitext(file_lower)[0]

                # Exact or substring match
                if query in file_lower or query in clean_name:
                    full_path = os.path.join(root, file)
                    try:
                        mtime = os.path.getmtime(full_path)
                    except OSError:
                        mtime = 0
                    candidates.append((full_path, mtime, len(file)))

    if candidates:
        # Sort by: 1. shortest matching name, 2. most recently modified
        candidates.sort(key=lambda x: (x[2], -x[1]))
        best_match = candidates[0][0]
        try:
            os.startfile(best_match)
            return True, f"Found and opening {os.path.basename(best_match)}."
        except Exception as e:
            print(f"[File Open Error]: {e}")
            return False, f"Failed to open {os.path.basename(best_match)}."

    return False, f"I could not locate any file matching {target_query}."

def find_and_open_file(target_query: str) -> tuple[bool, str]:
    """
    Locates and opens the exact requested file:
    1. Checks the active project workspace tree first (highest priority)
    2. Runs an exact-match search via Everything CLI (es.exe) across all drives
    3. Falls back to a deep user-folder crawl
    """
    query = target_query.strip().strip('"').strip("'")
    if not query:
        return False, "No file specified."

    # -------------------------------------------------------------
    # 1. PRIORITY 1: Check Current Project Workspace Tree
    # -------------------------------------------------------------
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for root, dirs, files in os.walk(project_root):
        # Skip internal cache directories
        dirs[:] = [d for d in dirs if d not in [".git", "venv", "__pycache__", ".idea"]]
        for f in files:
            if f.lower() == query.lower():
                full_path = os.path.join(root, f)
                try:
                    os.startfile(full_path)
                    return True, f"Opening project file {f}."
                except Exception as e:
                    print(f"[Project Open Error]: {e}")

    # -------------------------------------------------------------
    # 2. PRIORITY 2: Exact Match with Everything CLI (Whole PC)
    # -------------------------------------------------------------
    es_path = shutil.which("es.exe") or shutil.which("es")
    if es_path:
        try:
            # -w (whole word/filename), file: (files only), exact: (no prefix/suffix extensions)
            cmd = f'"{es_path}" -n 5 file: exact:"{query}"'
            output = subprocess.check_output(cmd, shell=True, text=True, errors="ignore").strip()

            if output:
                lines = [line.strip() for line in output.splitlines() if line.strip()]
                # Verify exact filename match to prevent .log / .tmp extensions
                for candidate in lines:
                    if os.path.basename(candidate).lower() == query.lower() and os.path.exists(candidate):
                        os.startfile(candidate)
                        return True, f"Opening {os.path.basename(candidate)}."
        except Exception as e:
            print(f"[ES Search Error]: {e}")

    # -------------------------------------------------------------
    # 3. PRIORITY 3: User Folders Scan
    # -------------------------------------------------------------
    search_roots = [
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
        os.path.expandvars(r"%USERPROFILE%\Downloads"),
        os.path.expandvars(r"%USERPROFILE%\Documents"),
        os.path.expandvars(r"%USERPROFILE%\Pictures"),
        os.path.expandvars(r"%USERPROFILE%\Videos"),
    ]

    for s_root in search_roots:
        if not os.path.exists(s_root):
            continue
        for root, dirs, files in os.walk(s_root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in ["appdata", "node_modules"]]
            for f in files:
                if f.lower() == query.lower():
                    full_path = os.path.join(root, f)
                    try:
                        os.startfile(full_path)
                        return True, f"Found and opening {f}."
                    except Exception as e:
                        print(f"[Crawl Open Error]: {e}")

    return False, f"Could not find an exact match for {query}."

def open_url(url: str) -> str:
    if not url.startswith("http"):
        url = f"https://{url}"
    webbrowser.open(url)
    return f"Opening {url}."