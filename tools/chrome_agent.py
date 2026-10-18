import os
import sys
import json
import subprocess
from typing import List, Dict, Optional, Tuple


class ChromeProfileManager:
    """
    Manages Google Chrome multi-profile discovery and launching for Project Libra.
    Inspects %LOCALAPPDATA%\\Google\\Chrome\\User Data\\Local State to extract
    account profiles, display names, and profile directory keys ('Default', 'Profile 1', etc.).
    """

    def __init__(self):
        self.local_state_path = self._locate_local_state()
        self.chrome_exe = self._locate_chrome_binary()

    @staticmethod
    def _locate_local_state() -> Optional[str]:
        candidates = [
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Local State"),
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\User Data\Local State"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
        return None

    @staticmethod
    def _locate_chrome_binary() -> Optional[str]:
        candidates = [
            os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
        return "chrome.exe"

    def get_profiles(self) -> List[Dict[str, str]]:
        """
        Reads Chrome profiles from Local State.
        Returns a list of dicts: [{'dir': 'Default', 'name': 'Chuah', 'email': '...'}, ...]
        """
        if not self.local_state_path or not os.path.isfile(self.local_state_path):
            return []

        try:
            with open(self.local_state_path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)

            info_cache = data.get("profile", {}).get("info_cache", {})
            profiles = []
            for profile_dir, p_info in info_cache.items():
                disp_name = (p_info.get("name") or "").strip()
                user_email = (p_info.get("user_name") or "").strip()
                gaia_name = (p_info.get("gaia_name") or "").strip()

                name = disp_name or gaia_name or profile_dir
                profiles.append({
                    "dir": profile_dir,
                    "name": name,
                    "email": user_email,
                })
            return profiles
        except Exception as e:
            print(f"[ChromeProfileManager Warning]: Failed to parse Chrome profiles: {e}")
            return []

    def resolve_profile(self, query: str) -> Optional[Dict[str, str]]:
        """
        Matches a natural language string ('Chuah', 'Paris', 'first', 'second', 'default')
        to an active Chrome profile.
        """
        profiles = self.get_profiles()
        if not profiles:
            return None

        q_low = (query or "").lower().strip()
        if not q_low:
            return None

        # Ordinal matches
        if any(w in q_low for w in ["first", "1st", "number 1", "one"]) and len(profiles) >= 1:
            return profiles[0]
        if any(w in q_low for w in ["second", "2nd", "number 2", "two"]) and len(profiles) >= 2:
            return profiles[1]
        if any(w in q_low for w in ["third", "3rd", "number 3", "three"]) and len(profiles) >= 3:
            return profiles[2]

        # Name / Email / Directory matches
        for p in profiles:
            p_name = p["name"].lower()
            p_email = p["email"].lower()
            p_dir = p["dir"].lower()

            if p_name in q_low or q_low in p_name:
                return p
            if p_email and (p_email in q_low or q_low in p_email):
                return p
            if p_dir in q_low or q_low in p_dir:
                return p

        return None

    def launch_chrome(self, profile_dir: Optional[str] = None, dry_run: bool = False) -> Tuple[bool, str]:
        """
        Launches Google Chrome, optionally with --profile-directory=<dir>.
        """
        target_exe = self.chrome_exe or "chrome.exe"
        cmd = [target_exe]
        if profile_dir:
            cmd.append(f"--profile-directory={profile_dir}")

        if dry_run:
            msg = f"Prepared Chrome launch with profile directory: {profile_dir or 'Default'}."
            return True, msg

        try:
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

            clean_env = os.environ.copy()
            clean_env.pop("VIRTUAL_ENV", None)
            clean_env.pop("PYTHONHOME", None)
            clean_env.pop("PYTHONPATH", None)

            subprocess.Popen(cmd, env=clean_env, creationflags=creationflags, close_fds=True)
            return True, f"Launched Google Chrome{' with ' + profile_dir if profile_dir else ''}."
        except Exception as e:
            return False, f"Failed to launch Chrome: {e}"
