import re
from typing import Dict, Any, Optional

TECHNICAL_ACRONYMS = {
    "CPU", "RAM", "GPU", "VRAM", "PDF", "DOCX", "TXT", "CSV", "USB",
    "API", "URL", "URI", "SQL", "RTX", "KLCC", "CLI", "GUI", "TTS",
    "STT", "VAD", "RAG", "LLM", "IDE", "OS", "PC", "AI", "SHA", "FPS"
}

HIGH_URGENCY_PATTERNS = [
    r"\b(?:hurry(?:\s+up)?|quick(?:ly)?|asap|immediately|urgent(?:ly)?|emergency)\b",
    r"\b(?:stop|kill|terminate|abort|shut\s+down|cancel|close)\b.*?\bright\s+now\b",
    r"\bright\s+now\b.*?\b(?:stop|kill|terminate|abort|shut\s+down|cancel|close)\b",
    r"\b(?:stop\s+it|kill\s+the\s+process|kill\s+it|abort\s+now|shut\s+it\s+down\s+now)\b",
    r"\b(?:still\s+not\s+working|failed\s+again|wrong\s+again|broken\s+again)\b",
    r"\b(?:close|kill|stop|terminate|mute)\b.*?\bnow\s*!",
    r"!!+"
]

RELAXED_PATTERNS = [
    r"\b(?:no\s+rush|take\s+your\s+time|whenever\s+you\s+can|at\s+your\s+leisure)\b",
    r"\b(?:chill|hang\s+out|casual(?:ly)?|tell\s+me\s+a\s+joke|just\s+curious|just\s+wondering)\b"
]


class SentimentAdapter:
    """
    Emotional Valence & Stress Modulation Engine for Project Libra v6.0.
    Analyzes user input for urgency, stress, or relaxed conversational tone,
    and dynamically modulates response cadence (enforcing <12-word tactical
    confirmations with zero banter during high-urgency states).
    """

    def __init__(self):
        pass

    def analyze_tone(self, user_input: str) -> Dict[str, Any]:
        """
        Detects urgency and emotional valence from user input.
        Returns:
          {
              "urgency": "high" | "normal" | "relaxed",
              "brevity_multiplier": float,
              "valence": str
          }
        """
        text = (user_input or "").strip()
        if not text:
            return {"urgency": "normal", "brevity_multiplier": 1.0, "valence": "neutral"}

        # 1. Check explicit high-urgency / stress regexes
        for pat in HIGH_URGENCY_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return {
                    "urgency": "high",
                    "brevity_multiplier": 0.35,
                    "valence": "stressed"
                }

        # 2. Check all-caps stress tokens (2+ uppercase words of len >= 3 that aren't tech acronyms)
        raw_words = re.findall(r"\b[A-Z]{3,}\b", text)
        shouting_words = [w for w in raw_words if w not in TECHNICAL_ACRONYMS]
        if len(shouting_words) >= 2:
            return {
                "urgency": "high",
                "brevity_multiplier": 0.35,
                "valence": "stressed"
            }

        # 3. Check relaxed / casual patterns
        for pat in RELAXED_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                return {
                    "urgency": "relaxed",
                    "brevity_multiplier": 1.25,
                    "valence": "relaxed"
                }

        return {
            "urgency": "normal",
            "brevity_multiplier": 1.0,
            "valence": "neutral"
        }

    def modulate_response(
        self,
        voice_text: str,
        tone_info: Optional[Dict[str, Any]] = None,
        action: str = "",
        target: str = ""
    ) -> str:
        """
        Adjusts spoken output according to detected urgency:
          - high: Strips all banter, preambles, and proactive follow-ups; enforces <12 words.
          - relaxed: Preserves full expressive SOUL personality.
          - normal: Standard balanced cadence.
        """
        info = tone_info or {"urgency": "normal", "brevity_multiplier": 1.0}
        urgency = info.get("urgency", "normal")

        clean = (voice_text or "").strip()
        if urgency != "high":
            return clean

        # High Urgency Mode: Zero banter, <12 words
        act_lower = (action or "").lower().strip()
        tgt_clean = (target or "").strip()

        if act_lower in ("close_app", "close_window", "kill_process"):
            if tgt_clean and tgt_clean.lower() not in ("active_window", "the process", "process"):
                short = f"Terminated {tgt_clean}."
            else:
                short = "Process terminated immediately."
            if len(short.split()) < 12:
                return short

        # Strip proactive suggestions ("By the way...", "You often...", "Would you like...")
        clean = re.split(
            r"\s+(?:By the way|You often|Would you like|Want me to|Should I)\b",
            clean,
            maxsplit=1,
            flags=re.IGNORECASE
        )[0].strip()

        # Strip conversational preambles
        clean = re.sub(
            r"^(?:Understood[\.,!\s]*|Sure thing[\.,!\s]*|Right away[\.,!\s]*|Of course[\.,!\s]*|Certainly[\.,!\s]*|No problem[\.,!\s]*)+",
            "",
            clean,
            flags=re.IGNORECASE
        ).strip()

        # Take only the first sentence
        first_sentence = re.split(r"(?<=[\.!\?])\s+", clean)[0].strip() if clean else "Done."

        words = first_sentence.split()
        if len(words) >= 12:
            truncated = " ".join(words[:9]).rstrip(",;:") + "."
            return truncated

        return first_sentence or "Done."

    def apply_brevity(
        self,
        voice_text: str,
        tone_info: Optional[Dict[str, Any]] = None,
        action: str = "",
        target: str = ""
    ) -> str:
        """Alias for modulate_response."""
        return self.modulate_response(voice_text, tone_info=tone_info, action=action, target=target)
