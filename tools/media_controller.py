import sys
import ctypes
from typing import Dict, Any

# Windows Virtual Key Codes for Hardware Media Control
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
KEYEVENTF_KEYUP = 0x0002


class MediaController:
    """
    Zero-Dependency Windows Media & System Volume Controller.
    Sends Windows Virtual Media Keys via user32.keybd_event for sub-millisecond,
    zero-credential global playback and volume control across Spotify, YouTube,
    browsers, and local media players.
    """

    def __init__(self):
        pass

    def _send_virtual_key(self, vk_code: int, dry_run: bool = False) -> bool:
        """Sends key-down and key-up event via user32.keybd_event."""
        if dry_run or sys.platform != "win32" or not hasattr(ctypes, "windll"):
            return True

        try:
            user32 = ctypes.windll.user32
            user32.keybd_event(vk_code, 0, 0, 0)
            user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            print(f"[MediaController Keybd Error]: {e}")
            return False

    def play_pause(self, dry_run: bool = False) -> Dict[str, Any]:
        """Toggles play / pause state globally."""
        success = self._send_virtual_key(VK_MEDIA_PLAY_PAUSE, dry_run=dry_run)
        return {
            "status": "success" if success else "error",
            "action": "play_pause",
            "vk_code": VK_MEDIA_PLAY_PAUSE,
            "voice_response": "Toggled playback."
        }

    def next_track(self, dry_run: bool = False) -> Dict[str, Any]:
        """Skips to the next track."""
        success = self._send_virtual_key(VK_MEDIA_NEXT_TRACK, dry_run=dry_run)
        return {
            "status": "success" if success else "error",
            "action": "next_track",
            "vk_code": VK_MEDIA_NEXT_TRACK,
            "voice_response": "Skipped to next track."
        }

    def prev_track(self, dry_run: bool = False) -> Dict[str, Any]:
        """Returns to the previous track."""
        success = self._send_virtual_key(VK_MEDIA_PREV_TRACK, dry_run=dry_run)
        return {
            "status": "success" if success else "error",
            "action": "prev_track",
            "vk_code": VK_MEDIA_PREV_TRACK,
            "voice_response": "Returned to previous track."
        }

    def volume_up(self, steps: int = 5, dry_run: bool = False) -> Dict[str, Any]:
        """Increases system volume by the specified number of steps."""
        for _ in range(max(1, steps)):
            self._send_virtual_key(VK_VOLUME_UP, dry_run=dry_run)
        return {
            "status": "success",
            "action": "volume_up",
            "vk_code": VK_VOLUME_UP,
            "steps": steps,
            "voice_response": f"Increased volume by {steps} steps."
        }

    def volume_down(self, steps: int = 5, dry_run: bool = False) -> Dict[str, Any]:
        """Decreases system volume by the specified number of steps."""
        for _ in range(max(1, steps)):
            self._send_virtual_key(VK_VOLUME_DOWN, dry_run=dry_run)
        return {
            "status": "success",
            "action": "volume_down",
            "vk_code": VK_VOLUME_DOWN,
            "steps": steps,
            "voice_response": f"Decreased volume by {steps} steps."
        }

    def mute_toggle(self, dry_run: bool = False) -> Dict[str, Any]:
        """Toggles system audio mute."""
        success = self._send_virtual_key(VK_VOLUME_MUTE, dry_run=dry_run)
        return {
            "status": "success" if success else "error",
            "action": "mute_toggle",
            "vk_code": VK_VOLUME_MUTE,
            "voice_response": "Toggled audio mute."
        }

    def mute(self, dry_run: bool = False) -> Dict[str, Any]:
        """Alias for mute_toggle."""
        return self.mute_toggle(dry_run=dry_run)

    def handle_command(self, text: str, dry_run: bool = False) -> Dict[str, Any]:
        """Parses natural language media instructions into hardware virtual key presses."""
        norm = (text or "").lower().strip()

        # Volume controls
        if any(k in norm for k in ["volume up", "louder", "turn up", "increase volume", "raise volume"]):
            return self.volume_up(steps=5, dry_run=dry_run)
        if any(k in norm for k in ["lower the volume", "volume down", "quieter", "turn down", "decrease volume", "lower volume"]):
            return self.volume_down(steps=5, dry_run=dry_run)
        if any(k in norm for k in ["mute", "unmute", "silence"]):
            return self.mute_toggle(dry_run=dry_run)

        # Track navigation
        if any(k in norm for k in ["skip this track", "skip track", "skip this song", "skip song", "next song", "next track", "skip this"]):
            return self.next_track(dry_run=dry_run)
        if any(k in norm for k in ["previous track", "previous song", "prev song", "prev track", "restart song", "last song"]):
            return self.prev_track(dry_run=dry_run)

        # Play / Pause toggles
        if any(k in norm for k in ["pause", "resume", "play", "stop music", "stop song"]):
            return self.play_pause(dry_run=dry_run)

        return self.play_pause(dry_run=dry_run)
