import sys
import collections
import time
from typing import Dict, Any

if not hasattr(sys, "_libra_clipboard_ring"):
    sys._libra_clipboard_ring = collections.deque(maxlen=20)

_CLIPBOARD_RING = sys._libra_clipboard_ring


def execute(args: dict, context: dict) -> Dict[str, Any]:
    """
    Manages a rolling ring buffer of clipboard text entries.
    Supports 'read', 'save', and 'clear' operations.
    """
    action = args.get("action", "read")
    text_to_save = args.get("text", "")

    if action == "save" and text_to_save:
        _CLIPBOARD_RING.appendleft({
            "text": text_to_save,
            "timestamp": time.strftime("%H:%M:%S")
        })
        return {
            "status": "success",
            "action": "save",
            "saved_text": text_to_save[:60],
            "buffer_size": len(_CLIPBOARD_RING),
            "voice_response": "Captured text into clipboard ring buffer."
        }

    if action == "clear":
        _CLIPBOARD_RING.clear()
        return {
            "status": "success",
            "action": "clear",
            "buffer_size": 0,
            "voice_response": "Clipboard ring buffer cleared."
        }

    # Default: read
    latest_item = _CLIPBOARD_RING[0] if _CLIPBOARD_RING else {"text": "", "timestamp": ""}
    return {
        "status": "success",
        "action": "read",
        "buffer_size": len(_CLIPBOARD_RING),
        "latest_item": latest_item.get("text", ""),
        "history": list(_CLIPBOARD_RING),
        "voice_response": f"Clipboard buffer holds {len(_CLIPBOARD_RING)} entries."
    }
