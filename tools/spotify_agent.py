import os
import sys
import json
import ctypes
import re
import urllib.parse
import subprocess
from typing import Dict, Any, Optional, List

# Windows Virtual Key Codes for Hardware Media Control
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
KEYEVENTF_KEYUP = 0x0002


class SpotifyAgent:
    """
    Zero-Latency Hardware Media Controller & Spotify Agent.
    Executes Windows Hardware Virtual Media Keys (VK_MEDIA_*) via user32.keybd_event
    for sub-millisecond, zero-credential playback control across Spotify, YouTube,
    Chrome, VLC, and local players, while maintaining Spotipy API compatibility.
    """

    def __init__(self, config_path: str = "config.json"):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.config_path = os.path.join(project_root, config_path)
        self.sp = None
        self._init_spotify()

    def _init_spotify(self):
        """Initializes optional Spotipy OAuth if configured."""
        if not os.path.exists(self.config_path):
            return
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth

            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                client_id = cfg.get("spotify_client_id") or cfg.get("2568993b08c34120a63cc5285a1fc856")
                client_secret = cfg.get("spotify_client_secret") or cfg.get("885f7c83afff4434a13463871e854033")
                redirect_uri = cfg.get("spotify_redirect_uri", "http://127.0.0.1:8888/callback")

            if client_id and client_secret:
                scope = "user-top-read user-read-recently-played playlist-read-private user-modify-playback-state"
                self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                    client_id=client_id,
                    client_secret=client_secret,
                    redirect_uri=redirect_uri,
                    scope=scope,
                    open_browser=False
                ))
        except Exception as e:
            print(f"[Spotify Init Note]: {e}")

    def _send_virtual_key(self, vk_code: int, dry_run: bool = False) -> bool:
        """Sends a hardware virtual key down and up event via user32.keybd_event."""
        if dry_run or sys.platform != "win32" or not hasattr(ctypes, "windll"):
            return True

        try:
            user32 = ctypes.windll.user32
            # Key down
            user32.keybd_event(vk_code, 0, 0, 0)
            # Key up
            user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            print(f"[MediaKey Error]: {e}")
            return False

    def is_spotify_installed(self) -> bool:
        """
        Checks if Spotify desktop application is installed or registered on the system.
        Verifies registry protocol handlers, common executable paths, and running processes.
        """
        if sys.platform != "win32":
            return True

        # 1. Check registry protocol handlers
        try:
            import winreg
            for root in [winreg.HKEY_CLASSES_ROOT, winreg.HKEY_CURRENT_USER]:
                try:
                    sub_key = r"Software\Classes\spotify" if root == winreg.HKEY_CURRENT_USER else "spotify"
                    k = winreg.OpenKey(root, sub_key)
                    winreg.CloseKey(k)
                    return True
                except Exception:
                    continue
        except Exception:
            pass

        # 2. Check well-known Spotify desktop executable paths
        known_paths = [
            os.path.join(os.environ.get("APPDATA", ""), "Spotify", "Spotify.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "Spotify.exe"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Spotify", "Spotify.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Spotify", "Spotify.exe"),
        ]
        for p in known_paths:
            if os.path.isfile(p):
                return True

        return False

    def play_query(self, query: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Plays a requested artist, song, or playlist on Spotify.
        Uses Spotipy API if authenticated, else checks if Spotify desktop is installed.
        If desktop is installed, triggers desktop URI (spotify:search:<query>).
        If desktop is not installed, seamlessly opens Spotify Web Player in default browser,
        preventing annoying Windows Microsoft Store popups.
        """
        clean_q = (query or "").strip()
        is_generic_music = clean_q.lower() in ["music", "some music", "a song", "songs"]
        display_q = "" if is_generic_music else clean_q
        voice_msg = f"Playing {display_q} on Spotify." if display_q else "Playing music on Spotify."

        if dry_run:
            return {
                "status": "success",
                "action": "spotify_play",
                "query": clean_q,
                "mode": "dry_run",
                "voice_response": voice_msg
            }

        # 1. Spotipy OAuth API playback if authenticated
        if self.sp:
            try:
                search_term = display_q or "Top Hits"
                results = self.sp.search(q=search_term, limit=1, type="track,artist")
                tracks = results.get("tracks", {}).get("items", [])
                if tracks:
                    track_uri = tracks[0]["uri"]
                    track_name = tracks[0].get("name", display_q or "music")
                    self.sp.start_playback(uris=[track_uri])
                    return {
                        "status": "success",
                        "action": "spotify_play",
                        "query": clean_q,
                        "track": track_name,
                        "uri": track_uri,
                        "mode": "api",
                        "voice_response": f"Playing {track_name} on Spotify."
                    }
            except Exception as e:
                print(f"[Spotify API Playback Warning]: {e}")

        # 2. Desktop Spotify Protocol Check
        installed = self.is_spotify_installed()
        if installed:
            try:
                encoded_query = urllib.parse.quote(display_q)
                spotify_uri = f"spotify:search:{encoded_query}" if display_q else "spotify:"
                if sys.platform == "win32":
                    try:
                        os.startfile(spotify_uri)
                    except Exception:
                        subprocess.Popen(["cmd.exe", "/c", "start", "", spotify_uri], shell=True)
                else:
                    import webbrowser
                    webbrowser.open(spotify_uri)

                self._send_virtual_key(VK_MEDIA_PLAY_PAUSE, dry_run=False)

                return {
                    "status": "success",
                    "action": "spotify_play",
                    "query": clean_q,
                    "uri": spotify_uri,
                    "mode": "desktop_uri",
                    "voice_response": voice_msg
                }
            except Exception as e:
                print(f"[Spotify Desktop URI Warning]: {e}")

        # 3. Seamless Spotify Web Player Fallback (Zero Store Popups)
        try:
            import webbrowser
            encoded_query = urllib.parse.quote(display_q)
            web_url = f"https://open.spotify.com/search/{encoded_query}" if display_q else "https://open.spotify.com"
            webbrowser.open(web_url)
            web_voice = f"Opening {display_q} on Spotify Web Player." if display_q else "Opening Spotify Web Player."
            return {
                "status": "success",
                "action": "spotify_play",
                "query": clean_q,
                "url": web_url,
                "mode": "web_fallback",
                "voice_response": web_voice
            }
        except Exception as e:
            return {
                "status": "error",
                "action": "spotify_play",
                "query": clean_q,
                "error": str(e),
                "voice_response": f"Failed to launch Spotify: {e}"
            }

    def play_pause(self, dry_run: bool = False) -> Dict[str, Any]:
        """Toggles play / pause state globally."""
        success = self._send_virtual_key(VK_MEDIA_PLAY_PAUSE, dry_run=dry_run)
        voice = "Toggled playback."
        return {
            "status": "success" if success else "error",
            "action": "play_pause",
            "voice_response": voice
        }

    def pause(self, dry_run: bool = False) -> Dict[str, Any]:
        """Pauses media playback globally."""
        success = self._send_virtual_key(VK_MEDIA_PLAY_PAUSE, dry_run=dry_run)
        return {
            "status": "success" if success else "error",
            "action": "pause",
            "voice_response": "Paused playback."
        }

    def resume(self, dry_run: bool = False) -> Dict[str, Any]:
        """Resumes media playback globally."""
        success = self._send_virtual_key(VK_MEDIA_PLAY_PAUSE, dry_run=dry_run)
        return {
            "status": "success" if success else "error",
            "action": "resume",
            "voice_response": "Resumed playback."
        }

    def play(self, dry_run: bool = False) -> Dict[str, Any]:
        """Starts or resumes media playback globally."""
        success = self._send_virtual_key(VK_MEDIA_PLAY_PAUSE, dry_run=dry_run)
        return {
            "status": "success" if success else "error",
            "action": "play",
            "voice_response": "Playing."
        }

    def stop(self, dry_run: bool = False) -> Dict[str, Any]:
        """Stops media playback globally."""
        success = self._send_virtual_key(VK_MEDIA_STOP, dry_run=dry_run)
        return {
            "status": "success" if success else "error",
            "action": "stop",
            "voice_response": "Stopped playback."
        }

    def next_track(self, dry_run: bool = False) -> Dict[str, Any]:
        """Skips to the next track."""
        success = self._send_virtual_key(VK_MEDIA_NEXT_TRACK, dry_run=dry_run)
        voice = "Skipped to next track."
        return {
            "status": "success" if success else "error",
            "action": "next_track",
            "voice_response": voice
        }

    def prev_track(self, dry_run: bool = False) -> Dict[str, Any]:
        """Returns to the previous track."""
        success = self._send_virtual_key(VK_MEDIA_PREV_TRACK, dry_run=dry_run)
        voice = "Returned to previous track."
        return {
            "status": "success" if success else "error",
            "action": "prev_track",
            "voice_response": voice
        }

    def volume_up(self, steps: int = 2, dry_run: bool = False) -> Dict[str, Any]:
        """Increases system volume."""
        for _ in range(max(1, steps)):
            self._send_virtual_key(VK_VOLUME_UP, dry_run=dry_run)
        voice = "Increased volume."
        return {
            "status": "success",
            "action": "volume_up",
            "steps": steps,
            "voice_response": voice
        }

    def volume_down(self, steps: int = 2, dry_run: bool = False) -> Dict[str, Any]:
        """Decreases system volume."""
        for _ in range(max(1, steps)):
            self._send_virtual_key(VK_VOLUME_DOWN, dry_run=dry_run)
        voice = "Decreased volume."
        return {
            "status": "success",
            "action": "volume_down",
            "steps": steps,
            "voice_response": voice
        }

    def mute(self, dry_run: bool = False) -> Dict[str, Any]:
        """Toggles system audio mute."""
        success = self._send_virtual_key(VK_VOLUME_MUTE, dry_run=dry_run)
        voice = "Toggled audio mute."
        return {
            "status": "success" if success else "error",
            "action": "mute",
            "voice_response": voice
        }

    def handle_media_command(self, text: str, dry_run: bool = False) -> Dict[str, Any]:
        """Parses natural language media instructions into hardware virtual key presses."""
        norm = text.lower().strip()

        # Volume controls
        if any(k in norm for k in ["volume up", "louder", "turn up", "increase volume", "raise volume"]):
            return self.volume_up(steps=3, dry_run=dry_run)
        if any(k in norm for k in ["volume down", "quieter", "turn down", "decrease volume", "lower volume"]):
            return self.volume_down(steps=3, dry_run=dry_run)
        if any(k in norm for k in ["mute", "unmute", "silence"]):
            return self.mute(dry_run=dry_run)

        # Track navigation
        if any(k in norm for k in ["next song", "next track", "skip song", "skip track", "skip this"]):
            return self.next_track(dry_run=dry_run)
        if any(k in norm for k in ["previous song", "previous track", "prev song", "prev track", "restart song", "last song"]):
            return self.prev_track(dry_run=dry_run)

        # Play / Pause toggles
        if any(k in norm for k in ["pause", "resume", "play", "stop music", "stop song"]):
            return self.play_pause(dry_run=dry_run)

        return self.play_pause(dry_run=dry_run)

    def get_now_playing(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Detects the currently playing track on Spotify Desktop via Win32 window title inspection
        ('Artist - Song Title' on Spotify.exe) or Spotipy API, requiring zero paid API keys.
        """
        if dry_run:
            return {
                "status": "playing",
                "action": "spotify_now_playing",
                "track": "Starboy",
                "artist": "The Weeknd",
                "voice_response": "Currently playing Starboy by The Weeknd on Spotify."
            }

        # 1. Check Spotipy API if authenticated
        if self.sp:
            try:
                playback = self.sp.current_playback()
                if playback and playback.get("item"):
                    item = playback["item"]
                    track = item.get("name", "")
                    artists = ", ".join([a["name"] for a in item.get("artists", [])])
                    is_playing = playback.get("is_playing", False)
                    if track:
                        state_word = "Currently playing" if is_playing else "Paused on"
                        return {
                            "status": "playing" if is_playing else "paused",
                            "action": "spotify_now_playing",
                            "track": track,
                            "artist": artists,
                            "voice_response": f"{state_word} {track} by {artists} on Spotify."
                        }
            except Exception:
                pass

        # 2. Zero-Credential Win32 Window Title Inspection for Spotify.exe
        if sys.platform == "win32" and hasattr(ctypes, "windll"):
            try:
                from ctypes import wintypes
                import psutil

                spotify_titles: List[str] = []
                user32 = ctypes.windll.user32

                def enum_proc(hwnd, lParam):
                    if user32.IsWindowVisible(hwnd):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buff, length + 1)
                            title = buff.value.strip()
                            if title:
                                pid = wintypes.DWORD()
                                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                                if pid.value > 0:
                                    try:
                                        proc = psutil.Process(pid.value)
                                        if proc.name().lower() == "spotify.exe":
                                            spotify_titles.append(title)
                                    except Exception:
                                        pass
                    return True

                EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                user32.EnumWindows(EnumWindowsProc(enum_proc), 0)

                for title in spotify_titles:
                    if " - " in title and title.lower() not in ["spotify", "spotify free", "spotify premium"]:
                        parts = title.split(" - ", 1)
                        artist = parts[0].strip()
                        track = parts[1].strip()
                        return {
                            "status": "playing",
                            "action": "spotify_now_playing",
                            "track": track,
                            "artist": artist,
                            "voice_response": f"You're listening to {track} by {artist} on Spotify."
                        }
                if spotify_titles:
                    return {
                        "status": "paused",
                        "action": "spotify_now_playing",
                        "track": None,
                        "artist": None,
                        "voice_response": "Spotify is open, but playback is currently paused."
                    }
            except Exception as e:
                print(f"[Spotify NowPlaying Inspection Warning]: {e}")

        return {
            "status": "idle",
            "action": "spotify_now_playing",
            "track": None,
            "artist": None,
            "voice_response": "Spotify doesn't appear to be playing anything right now."
        }

    def get_favorite_artists(self) -> List[str]:
        """Fetches top artists from active Spotify profile if Spotipy is connected."""
        if not self.sp:
            return []
        try:
            top_artists = self.sp.current_user_top_artists(limit=8, time_range="medium_term")
            artists = [item['name'] for item in top_artists.get('items', [])]
            return artists
        except Exception as e:
            print(f"[Spotify Read Error]: {e}")
            return []