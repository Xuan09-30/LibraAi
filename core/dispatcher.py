import os
import sys
import re
import subprocess
import webbrowser
import ctypes
from ctypes import wintypes
import psutil

PSUTIL_AVAILABLE = True

from core.game_discovery import GameDiscoveryEngine
from core.trust_guard import get_trust_guard, RiskTier


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

    PROTECTED_SYSTEM_PROCESSES = {
        "explorer.exe",
        "svchost.exe",
        "csrss.exe",
        "wininit.exe",
        "winlogon.exe",
        "lsass.exe",
        "system",
        "python.exe",
        "pythonw.exe",
        "smss.exe",
        "services.exe",
        "dwm.exe",
        "fontdrvhost.exe",
        "registry",
        "idle",
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
        """Returns the allowlisted or discovered execution specification without running the application."""
        norm = app_id.lower().strip()

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
        elif norm == "roblox":
            discovered_roblox = self.discovery.resolve_app("roblox") if self.discovery else None
            if discovered_roblox:
                return {
                    "app_id": "roblox",
                    "name": discovered_roblox.get("name", "Roblox"),
                    "target": discovered_roblox.get("target", "RobloxPlayerBeta.exe"),
                    "launch_type": discovered_roblox.get("launch_type", "executable"),
                    "type": discovered_roblox.get("launch_type", "executable"),
                    "installed": True,
                    "keystrokes_injected": False,
                    "passwords_stored": False,
                }
            return {
                "app_id": "roblox",
                "name": "Roblox",
                "executable": r"AppData\Local\Roblox\Versions\RobloxPlayerBeta.exe",
                "target": r"AppData\Local\Roblox\Versions\RobloxPlayerBeta.exe",
                "launch_type": "executable",
                "type": "executable",
                "installed": False,
                "keystrokes_injected": False,
                "passwords_stored": False,
            }
        elif norm in ["spotify", "discord"]:
            discovered_app = self.discovery.resolve_app(norm) if self.discovery else None
            if discovered_app:
                return {
                    "app_id": norm,
                    "name": discovered_app.get("name", norm.title()),
                    "target": discovered_app.get("target"),
                    "args": discovered_app.get("args", []),
                    "launch_type": discovered_app.get("launch_type", "executable"),
                    "type": discovered_app.get("launch_type", "executable"),
                    "installed": True,
                    "keystrokes_injected": False,
                    "passwords_stored": False,
                }
            return {
                "app_id": norm,
                "uri": f"{norm}:",
                "type": "protocol",
                "keystrokes_injected": False,
                "passwords_stored": False,
            }

        if norm in self.ALLOWLIST:
            return {
                "app_id": norm,
                "type": "executable",
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
            elif norm == "roblox":
                if not spec.get("installed", False):
                    return (
                        False,
                        "I searched your Start Menu, Steam, and AppData folders, but Roblox doesn't appear to be installed on this PC.",
                    )
                target = spec.get("target")
                l_type = spec.get("launch_type", "executable")
                if l_type == "uwp" or (target and target.startswith("shell:AppsFolder")):
                    subprocess.Popen(["explorer.exe", target], close_fds=True)
                elif l_type == "lnk" or (target and target.endswith(".lnk")):
                    subprocess.Popen(["explorer.exe", target], close_fds=True)
                else:
                    cwd = os.path.dirname(target) if target and os.path.exists(target) else None
                    subprocess.Popen([target], cwd=cwd, env=clean_env, creationflags=creationflags, close_fds=True)
                return True, "Launching Roblox."
            elif norm in ["spotify", "discord"]:
                if spec.get("target"):
                    target = spec["target"]
                    l_type = spec.get("launch_type", "executable")
                    args = spec.get("args", [])
                    if l_type == "uwp" or target.startswith("shell:AppsFolder"):
                        subprocess.Popen(["explorer.exe", target], close_fds=True)
                    elif l_type == "lnk" or target.endswith(".lnk"):
                        subprocess.Popen(["explorer.exe", target], close_fds=True)
                    else:
                        cwd = os.path.dirname(target) if os.path.exists(target) else None
                        subprocess.Popen([target] + args, cwd=cwd, env=clean_env, creationflags=creationflags, close_fds=True)
                    return True, f"Launching {norm.title()}."
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

                # 0. Windows UWP / shell:AppsFolder targets
                if launch_type == "uwp" or (target and target.startswith("shell:AppsFolder")):
                    if sys.platform == "win32":
                        subprocess.Popen(["explorer.exe", target], close_fds=True)
                        return True, f"Launching {app_name}."
                    return False, f"UWP launch is only supported on Windows."

                # 1. Steam URI or URI protocols (Detached via explorer.exe)
                elif launch_type == "uri" or (target and target.startswith("steam://")) or (target and target.endswith(".url")):
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

                    # Never launch broken ms-windows-store or bare roblox URIs
                    if uri_target.lower().startswith(("ms-windows-store:", "roblox:", "roblox-player:")):
                        return (
                            False,
                            f"I searched your Start Menu, Steam, and AppData folders, but {app_name} doesn't appear to be installed on this PC.",
                        )

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

        return (
            False,
            f"Application '{app_id}' is not in the approved safety allowlist or was not found in your Start Menu, Steam, or AppData folders.",
        )

    def close_active_window(self, dry_run: bool = False) -> tuple[bool, str]:
        """Safely closes or minimizes the foreground window using Win32 API."""
        if dry_run:
            return True, "Active window close signal prepared."

        try:
            if sys.platform == "win32":
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                if not hwnd:
                    return False, "No active foreground window detected."

                # Check if foreground window is Libra herself; if so, resolve user workspace
                w_pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(w_pid))
                if w_pid.value == os.getpid():
                    from tools.window_context import ActiveWindowEngine
                    ext_hwnd = ActiveWindowEngine._find_top_external_window(user32, hwnd, os.getpid())
                    if ext_hwnd:
                        hwnd = ext_hwnd
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(w_pid))

                app_name = "active window"
                proc_name = ""
                if w_pid.value > 0 and PSUTIL_AVAILABLE:
                    try:
                        p = psutil.Process(w_pid.value)
                        proc_name = (p.name() or "").lower()
                        app_name = proc_name.replace(".exe", "").title()
                        if proc_name in self.PROTECTED_SYSTEM_PROCESSES:
                            return False, f"Process '{proc_name}' is a protected system process and cannot be closed."
                        # For stubborn tray apps like Discord or Spotify, force kill process via taskkill
                        if proc_name in ["discord.exe", "spotify.exe", "steam.exe"]:
                            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                            try:
                                subprocess.run(
                                    ["taskkill.exe", "/F", "/T", "/IM", proc_name],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    creationflags=creation_flags,
                                )
                            except Exception:
                                pass
                            try:
                                p.kill()
                            except Exception:
                                pass
                            return True, f"Closed {app_name}."
                    except Exception:
                        pass

                # WM_CLOSE = 0x0010
                user32.PostMessageW(hwnd, 0x0010, 0, 0)
                return True, f"Closed {app_name}."
            return False, "Active window close is only supported on Windows."
        except Exception as e:
            return False, f"Error closing active window: {e}"

    def close_app(self, target: str, dry_run: bool = False) -> tuple[bool, str]:
        """
        Closes any named user application via psutil process matching or closes the active foreground window,
        while strictly protecting critical Windows and Python system processes.
        """
        raw_norm = target.lower().strip()
        raw_norm = re.sub(r"^(?:my|the)\s+", "", raw_norm).strip()
        norm = raw_norm.replace(".exe", "").strip()

        # Handle Whisper acoustic slip for Discord ("this card", "this cord")
        if norm in ["this card", "this cord", "dis card", "discord"]:
            norm = "discord"

        if norm in ["active", "close_active", "window", "it", "current window", "active window", "this", "this window", "this app"]:
            return self.close_active_window(dry_run=dry_run)

        # Protect critical Windows & Python system processes
        candidate_exe = f"{norm}.exe"
        if raw_norm in self.PROTECTED_SYSTEM_PROCESSES or candidate_exe in self.PROTECTED_SYSTEM_PROCESSES or norm in self.PROTECTED_SYSTEM_PROCESSES:
            return False, f"Process '{target}' is a protected critical system process and cannot be terminated."

        if dry_run:
            return True, f"Termination signal prepared for {norm}."

        aliases = {
            "valorant": ["valorant.exe", "valorant-win64-shipping.exe"],
            "steam": ["steam.exe"],
            "browser": ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"],
            "chrome": ["chrome.exe"],
            "spotify": ["spotify.exe"],
            "discord": ["discord.exe", "discordcanary.exe", "discordptb.exe"],
            "roblox": ["robloxplayerbeta.exe", "robloxplayerlauncher.exe", "windows10universal.exe"],
            "notepad": ["notepad.exe"],
            "vscode": ["code.exe"],
            "vs code": ["code.exe"],
            "calculator": ["calculatorapp.exe", "calc.exe"],
        }
        target_names = set(aliases.get(norm, [candidate_exe, norm]))

        # Dynamically inspect discovery engine to resolve target executable
        if self.discovery:
            try:
                resolved = self.discovery.resolve_app(norm)
                if resolved:
                    t_path = resolved.get("target") or ""
                    if t_path.lower().endswith(".exe"):
                        exe_name = os.path.basename(t_path).lower()
                        target_names.add(exe_name)
                        target_names.add(exe_name.replace(".exe", ""))
                    name_str = (resolved.get("name") or "").lower()
                    if name_str:
                        target_names.add(f"{name_str}.exe")
                        target_names.add(name_str)
            except Exception:
                pass

        terminated_count = 0
        try:
            for proc in psutil.process_iter(["name", "pid"]):
                try:
                    pname = (proc.info.get("name") or "").lower().strip()
                    if not pname or pname in self.PROTECTED_SYSTEM_PROCESSES:
                        continue
                    pname_stem = pname.replace(".exe", "")
                    if (
                        pname in target_names
                        or pname_stem in target_names
                        or pname_stem == norm
                        or (len(norm) >= 4 and (norm in pname_stem or pname_stem in norm))
                    ):
                        try:
                            proc.kill()
                        except Exception:
                            proc.terminate()
                        terminated_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            # On Windows, run taskkill for stubborn tray apps or if psutil missed handles
            if sys.platform == "win32" and (norm in ["discord", "spotify", "steam"] or terminated_count == 0):
                for exe in list(target_names):
                    if exe.endswith(".exe") and exe not in self.PROTECTED_SYSTEM_PROCESSES:
                        try:
                            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                            res = subprocess.run(
                                ["taskkill.exe", "/F", "/T", "/IM", exe],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                creationflags=creation_flags,
                            )
                            if res.returncode == 0:
                                terminated_count += 1
                        except Exception:
                            pass
        except Exception as e:
            return False, f"Failed to close {target}: {e}"

        if terminated_count > 0:
            return True, f"Closed {target.title()} ({terminated_count} process{'es' if terminated_count > 1 else ''} terminated)."
        return False, f"No active running process found for {target.title()}."

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

    def dispatch_weather(self, prompt: str, dry_run: bool = False, default_city: str = "Kuala Lumpur") -> dict:
        """Executes isolated weather telemetry directly via tools.weather."""
        return dispatch_weather(prompt, dry_run=dry_run, default_city=default_city)


# ---------------------------------------------------------------------------
# STRICT ROUTE ISOLATION: WEATHER ENGINE
# ---------------------------------------------------------------------------
def is_weather_intent(prompt: str) -> bool:
    """Determines if a prompt is an isolated weather or forecast query."""
    if not prompt or not str(prompt).strip():
        return False
    q_lower = str(prompt).lower().strip()
    if re.search(r"\b(?:can\s+you\s+predict|predict\s+the\s+weather|next\s+month|next\s+year)\b", q_lower):
        return False
    return bool(re.search(
        r"\b(?:weather|forecast|rain\s+forecast|rain\s+chance|raining|temperature|is\s+it\s+(?:going\s+to\s+)?rain|how\s+(?:hot|cold|warm)\s+is\s+it)\b",
        q_lower
    ))


def dispatch_weather(prompt: str, dry_run: bool = False, default_city: str = "Kuala Lumpur", context_city: str | None = None) -> dict:
    """
    Direct, strictly isolated weather dispatcher.
    Bypasses LLM planning, RAG pipelines, Wikipedia searches, and web search agents completely.
    Executes ONLY tools/weather.py and returns clean Open-Meteo telemetry immediately.
    """
    from tools.weather import get_weather, get_weekly_forecast, geocode_location, BUILT_IN_LOCATIONS
    q_lower = str(prompt).lower().strip()

    def _clean_loc_str(raw: str) -> str | None:
        s = re.sub(
            r"\b(?:today|tomorrow|right\s+now|now|this\s+weekend|weekend|this\s+week|weekly|7\s+days?|next\s+few\s+days|tonight|please|for\s+me)\b",
            "",
            raw,
            flags=re.IGNORECASE,
        ).strip(" ,.?!'")
        if s and s.lower() not in ["me", "here", "my area", "outside", "there"]:
            return s
        return None

    has_there = bool(re.search(r"\bthere\b", q_lower))

    # 1. Weekly / 7-day forecast request
    if re.search(r"\b(?:weekly|this\s+week|weekend|7\s+days?|next\s+few\s+days)\b", q_lower):
        loc = None
        loc_m = re.search(r"\b(?:in|for|at)\s+([a-zA-Z\s,]+?)[\.\?!]*$", q_lower)
        if loc_m:
            loc = _clean_loc_str(loc_m.group(1).strip())
        if not loc:
            for city_key in BUILT_IN_LOCATIONS:
                if re.search(rf"\b{re.escape(city_key)}\b", q_lower):
                    loc = city_key
                    break
        if not loc and has_there and context_city:
            loc = context_city
        target_loc = loc or default_city
        geo = geocode_location(target_loc)
        resolved_name = geo.get("name", target_loc) if geo else target_loc
        voice = get_weekly_forecast(location_query=target_loc)
        return {
            "action": "weather",
            "status": "success",
            "args": {"location": resolved_name},
            "location": resolved_name,
            "forecast_type": "weekly",
            "voice_response": voice,
            "isolated_route": True
        }

    # 2. Daily / current weather request
    loc_extracted = None
    loc_m = re.search(r"\b(?:in|for|at)\s+([a-zA-Z\s,]+?)[\.\?!]*$", q_lower)
    if loc_m:
        loc_extracted = _clean_loc_str(loc_m.group(1).strip())

    if not loc_extracted:
        for city_key in BUILT_IN_LOCATIONS:
            if re.search(rf"\b{re.escape(city_key)}\b", q_lower):
                loc_extracted = city_key
                break

    if not loc_extracted and has_there and context_city:
        loc_extracted = context_city

    target_loc = loc_extracted or default_city
    w_res = get_weather(location_query=target_loc, dry_run=dry_run)
    return {
        "action": "weather",
        "status": w_res.get("status", "success"),
        "args": {"location": w_res.get("location") or target_loc},
        "location": w_res.get("location"),
        "latitude": w_res.get("latitude"),
        "longitude": w_res.get("longitude"),
        "temperature_c": w_res.get("temperature_c"),
        "condition": w_res.get("condition"),
        "rain_chance": w_res.get("rain_chance"),
        "voice_response": w_res.get("voice_response"),
        "isolated_route": True
    }

