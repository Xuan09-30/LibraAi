import os
import sys
import json
import ctypes
import re
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

    def play_pause(self, dry_run: bool = False) -> Dict[str, Any]:
        """Toggles play / pause state globally."""
        success = self._send_virtual_key(VK_MEDIA_PLAY_PAUSE, dry_run=dry_run)
        voice = "Toggled playback."
        return {
            "status": "success" if success else "error",
            "action": "play_pause",
            "voice_response": voice
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