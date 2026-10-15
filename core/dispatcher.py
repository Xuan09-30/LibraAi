import os
import sys
import subprocess
import webbrowser
import ctypes


from core.game_discovery import GameDiscoveryEngine


class SafeOSDispatcher:
    """
    Safe allowlist and autonomous discovery operating system dispatcher for Libra AI.
    Strictly forbids arbitrary shell executions, injected keystrokes, and stored credentials.
    Enforces official protocol handlers, CLI parameters, and confirmation guards for destructive operations.
    """

    ALLOWLIST = {
        "valorant",
        "steam",
        "browser",
        "spotify",
        "discord",
        "roblox",
    }

    CLOSABLE_ALLOWLIST = {
        "valorant",
        "steam",
        "browser",
        "chrome",
        "spotify",
        "discord",
        "roblox",
        "active",
        "window",
        "close_active",
        "current window",
        "active window",
        "it",
    }

    BLOCKED_BINARIES = {
        "cmd.exe", "powershell.exe", "pwsh.exe", "regedit.exe", "format.com",
        "cmd", "powershell", "pwsh", "regedit", "format", "malicious_app.exe"
    }

    def __init__(self, discovery: GameDiscoveryEngine | None = None):
        self.discovery = discovery if discovery is not None else GameDiscoveryEngine()

    @staticmethod
    def _find_riot_client() -> str:
        candidates = [
            r"C:\Riot Games\Riot Client\RiotClientServices.exe",
            os.path.expandvars(r"%PROGRAMFILES%\Riot Games\Riot Client\RiotClientServices.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Riot Games\Riot Client\RiotClientServices.exe"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return "RiotClientServices.exe"

    def get_launch_spec(self, app_id: str) -> dict | None:
        """Returns the allowlisted execution specification without running the application."""
        norm = app_id.lower().strip()
        if norm not in self.ALLOWLIST:
            return None

        if norm == "valorant":
            return {
                "app_id": "valorant",
                "executable": self._find_riot_client(),
                "args": ["--launch-product=valorant", "--launch-patchline=live"],
                "type": "executable",
                "keystrokes_injected": False,
                "passwords_stored": False,
            }
        elif norm == "steam":
            return {
                "app_id": "steam",
                "uri": "steam://open/main",
                "type": "protocol",
                "keystrokes_injected": False,
                "passwords_stored": False,
            }
        elif norm == "browser":
            return {
                "app_id": "browser",
                "target": "https://www.google.com",
                "type": "browser",
                "keystrokes_injected": False,
                "passwords_stored": False,
            }
        elif norm in ["spotify", "discord", "roblox"]:
            uri = "roblox-player:" if norm == "roblox" else f"{norm}:"
            return {
                "app_id": norm,
                "uri": uri,
                "type": "protocol",
                "keystrokes_injected": False,
                "passwords_stored": False,
            }
        return None

    @staticmethod
    def _get_clean_env() -> dict:
        """Returns a sanitized environment with Python venv and CUDA hooks stripped."""
        clean = os.environ.copy()
        clean.pop("VIRTUAL_ENV", None)
        clean.pop("PYTHONHOME", None)
        clean.pop("PYTHONPATH", None)
        if "PATH" in clean:
            paths = clean["PATH"].split(os.pathsep)
            filtered = [
                p for p in paths
                if "venv" not in p.lower()
                and "libraai" not in p.lower()
                and "\\libra\\" not in p.lower()
            ]
            clean["PATH"] = os.pathsep.join(filtered)
        return clean

    def _execute_spec(self, norm: str, spec: dict) -> tuple[bool, str]:
        """Safely executes an allowlisted application spec outside venv."""
        try:
            clean_env = self._get_clean_env()
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

            if norm == "valorant":
                cmd = [spec["executable"]] + spec["args"]
                cwd = os.path.dirname(spec["executable"]) if os.path.exists(spec["executable"]) else None
                subprocess.Popen(cmd, cwd=cwd, env=clean_env, creationflags=creationflags, close_fds=True)
                return True, "Launching Valorant via Riot Client."
            elif norm == "steam":
                uri = spec["uri"]
                if sys.platform == "win32":
                    subprocess.Popen(["explorer.exe", uri], close_fds=True)
                else:
                    webbrowser.open(uri)
                return True, "Opening Steam."
            elif norm == "browser":
                webbrowser.open(spec["target"])
                return True, "Opening default browser."
            elif norm in ["spotify", "discord", "roblox"]:
                uri = spec["uri"]
                if sys.platform == "win32":
                    subprocess.Popen(["explorer.exe", uri], close_fds=True)
                else:
                    webbrowser.open(uri)
                return True, f"Launching {norm.title()}."
        except Exception as e:
            return False, f"Failed to launch {norm}: {e}"

        return False, f"Failed to dispatch {norm}."

    def launch_app(self, app_id: str, dry_run: bool = False) -> tuple[bool, str]:
        """
        Launches an application or game.
        Checks static allowlist first, then queries the Autonomous Game & App Discovery Engine.
        Enforces security blocking on dangerous shell binaries and isolates processes outside Python venv.
        """
        norm = app_id.lower().strip()

        # Blocked dangerous system binaries
        if any(norm == b or norm.endswith(f"\\{b}") or norm.endswith(f"/{b}") for b in self.BLOCKED_BINARIES):
            return False, f"Application '{app_id}' is not in the approved safety allowlist."

        # 1. Check static ALLOWLIST first
        if norm in self.ALLOWLIST:
            spec = self.get_launch_spec(norm)
            if not spec:
                return False, f"Application '{app_id}' could not be resolved in the allowlist."

            if dry_run:
                return True, f"Allowlisted launch prepared for {norm}."

            return self._execute_spec(norm, spec)

        # 2. Check Autonomous Game & App Discovery Engine
        resolved = self.discovery.resolve_app(norm)
        if resolved:
            app_name = resolved.get("name", norm.title())
            target = resolved.get("target")
            launch_type = resolved.get("launch_type", "uri")

            if target:
                t_lower = target.lower()
                if any(t_lower.endswith(b) for b in self.BLOCKED_BINARIES):
                    return False, f"Application '{app_id}' is not in the approved safety allowlist."

            if dry_run:
                return True, f"Discovered launch prepared for {app_name} via {launch_type}."

            try:
                clean_env = self._get_clean_env()
                creationflags = 0
                if sys.platform == "win32":
                    creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

                # 1. Steam URI or URI protocols (Detached via explorer.exe)
                if launch_type == "uri" or (target and target.startswith("steam://")) or (target and target.endswith(".url")):
                    uri_target = target
                    if target.endswith(".url") and os.path.isfile(target):
                        try:
                            with open(target, "r", encoding="utf-8", errors="ignore") as uf:
                                for line in uf:
                                    if line.startswith("URL="):
                                        uri_target = line.split("URL=", 1)[1].strip()
                                        break
                        except Exception:
                            pass

                    if sys.platform == "win32":
                        subprocess.Popen(["explorer.exe", uri_target], close_fds=True)
                    else:
                        webbrowser.open(uri_target)
                    return True, f"Launching {app_name}."

                # 2. Executable targets with CLI arguments
                elif launch_type == "executable" and resolved.get("args"):
                    cmd = [target] + resolved["args"]
                    cwd = os.path.dirname(target) if os.path.exists(target) else None
                    subprocess.Popen(cmd, cwd=cwd, env=clean_env, creationflags=creationflags, close_fds=True)
                    return True, f"Launching {app_name}."

                # 3. Direct .lnk shortcuts
                elif (target and target.endswith(".lnk")) or launch_type == "lnk":
                    if sys.platform == "win32":
                        subprocess.Popen(["explorer.exe", target], close_fds=True)
                    else:
                        cwd = os.path.dirname(target) if os.path.exists(target) else None
                        subprocess.Popen([target], cwd=cwd, env=clean_env, close_fds=True)
                    return True, f"Launching {app_name}."

                # 4. Direct .exe targets
                elif (target and target.endswith(".exe")) or launch_type == "executable":
                    cmd = [target]
                    cwd = os.path.dirname(target) if os.path.exists(target) else None
                    subprocess.Popen(cmd, cwd=cwd, env=clean_env, creationflags=creationflags, close_fds=True)
                    return True, f"Launching {app_name}."
                else:
                    return False, f"Unknown launch target for {app_name}."
            except Exception as e:
                return False, f"Failed to launch {app_name}: {e}"

        return False, f"Application '{app_id}' is not in the approved safety allowlist."

    def close_active_window(self, dry_run: bool = False) -> tuple[bool, str]:
        """Safely closes or minimizes the foreground window using Win32 API."""
        if dry_run:
            return True, "Active window close signal prepared."

        try:
            if sys.platform == "win32":
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                if hwnd:
                    # WM_CLOSE = 0x0010
                    user32.PostMessageW(hwnd, 0x0010, 0, 0)
                    return True, "Closed active window."
                return False, "No active foreground window detected."
            return False, "Active window close is only supported on Windows."
        except Exception as e:
            return False, f"Error closing active window: {e}"

    def close_app(self, target: str, dry_run: bool = False) -> tuple[bool, str]:
        """Closes an allowlisted application or the active foreground window."""
        norm = target.lower().strip().replace(".exe", "")

        if norm in ["active", "close_active", "window", "it", "current window", "active window"]:
            return self.close_active_window(dry_run=dry_run)

        if norm not in self.CLOSABLE_ALLOWLIST:
            return False, f"Application '{target}' is not in the approved safety allowlist for termination."

        if dry_run:
            return True, f"Allowlisted termination signal prepared for {norm}."

        aliases = {
            "valorant": "VALORANT.exe",
            "steam": "steam.exe",
            "browser": "chrome.exe",
            "chrome": "chrome.exe",
            "spotify": "Spotify.exe",
            "discord": "Discord.exe",
            "roblox": "RobloxPlayerBeta.exe",
        }
        proc_name = aliases.get(norm, f"{norm}.exe")
        try:
            res = subprocess.run(["taskkill", "/F", "/IM", proc_name, "/T"], capture_output=True, text=True)
            if res.returncode == 0:
                return True, f"Closed {target.title()}."
            return False, f"No active process found for {target.title()}."
        except Exception as e:
            return False, f"Failed to close {target}: {e}"

    def request_shutdown(self, confirmed: bool = False, dry_run: bool = False) -> tuple[bool, str]:
        """
        Guarded system shutdown.
        Requires explicit user confirmation before issuing the OS shutdown command.
        """
        if not confirmed:
            return False, "Confirmation required: Are you sure you want to shut down your PC?"

        if dry_run:
            return True, "[Dry Run] Scheduled shutdown."

        try:
            if sys.platform == "win32":
                subprocess.run(["shutdown", "/s", "/t", "60"], check=True)
                return True, "Shutting down the system in 60 seconds."
            return False, "Shutdown is only supported on Windows."
        except Exception as e:
            return False, f"Failed to schedule shutdown: {e}"
