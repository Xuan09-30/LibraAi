import os
import sys
import subprocess
import webbrowser
import ctypes


class SafeOSDispatcher:
    """
    Safe allowlist-only operating system dispatcher for Libra AI.
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

    def launch_app(self, app_id: str, dry_run: bool = False) -> tuple[bool, str]:
        """Launches an allowlisted application using verified arguments and protocol handlers."""
        norm = app_id.lower().strip()

        if norm not in self.ALLOWLIST:
            return False, f"Application '{app_id}' is not in the approved safety allowlist."

        spec = self.get_launch_spec(norm)
        if not spec:
            return False, f"Application '{app_id}' could not be resolved in the allowlist."

        if dry_run:
            return True, f"Allowlisted launch prepared for {norm}."

        try:
            if norm == "valorant":
                cmd = [spec["executable"]] + spec["args"]
                subprocess.Popen(cmd)
                return True, "Launching Valorant via Riot Client."
            elif norm == "steam":
                if hasattr(os, "startfile"):
                    os.startfile(spec["uri"])
                else:
                    webbrowser.open(spec["uri"])
                return True, "Opening Steam."
            elif norm == "browser":
                webbrowser.open(spec["target"])
                return True, "Opening default browser."
            elif norm in ["spotify", "discord", "roblox"]:
                if hasattr(os, "startfile"):
                    os.startfile(spec["uri"])
                else:
                    webbrowser.open(spec["uri"])
                return True, f"Launching {norm.title()}."
        except Exception as e:
            return False, f"Failed to launch {app_id}: {e}"

        return False, f"Failed to dispatch {app_id}."

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
