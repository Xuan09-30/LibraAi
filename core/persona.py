import os
import re
import collections
from typing import Dict, Any, Optional, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class PersonaEngine:
    """
    Evolving Personality & Anti-Repetition Phrasing Engine for Project Libra.
    Loads SOUL.md and USER.md, dynamically humanizes tool responses to prevent
    robotic repetition (<2ms local pool selection), and persists user-commanded
    personality adjustments into SOUL.md.
    """

    def __init__(
        self,
        soul_path: str = "assets/SOUL.md",
        user_path: str = "assets/USER.md"
    ):
        self.soul_path = os.path.join(PROJECT_ROOT, soul_path)
        self.user_path = os.path.join(PROJECT_ROOT, user_path)
        self.recent_responses: collections.deque = collections.deque(maxlen=10)
        self.soul_content = ""
        self.user_content = ""
        self.load_documents()

    def load_documents(self):
        """Loads or creates SOUL.md and USER.md."""
        if os.path.exists(self.soul_path):
            try:
                with open(self.soul_path, "r", encoding="utf-8") as f:
                    self.soul_content = f.read()
            except Exception as e:
                print(f"[PersonaEngine SOUL Load Warning]: {e}")
        else:
            self.soul_content = "# LIBRA SOUL\n- Wit: Balanced\n- Tone: Natural, confident\n"

        if os.path.exists(self.user_path):
            try:
                with open(self.user_path, "r", encoding="utf-8") as f:
                    self.user_content = f.read()
            except Exception as e:
                print(f"[PersonaEngine USER Load Warning]: {e}")
        else:
            self.user_content = "# USER PROFILE\n"

    def get_system_prompt_addon(self) -> str:
        """Injects concise SOUL rules and user preferences into LLM system prompts."""
        recent_str = " | ".join(list(self.recent_responses)[-3:]) if self.recent_responses else "None"
        addon = (
            "--- PERSONALITY, IDENTITY & ECOSYSTEM (SOUL.md) ---\n"
            "Persona: Sharp, effortlessly capable, subtly witty cybernetic partner (Jarvis-inspired). Never stiff or corporate.\n"
            "Ecosystem & Website Awareness: You are Project Libra. You run locally on your user's Home PC (RTX 5060 Ti GPU) and are also accessible remotely on your user's Samsung smartphone and laptops via your official Tailscale web interface at https://libra-beta.note-loggerhead.ts.net/. When the user asks about your website, phone app, or Tailscale connection, you KNOW you have this web/mobile interface.\n"
            "Multimodal Capabilities: You can inspect PC screens, analyze photos and images using vision AI (Qwen2.5-VL), read and summarize uploaded PDFs and documents, and converse in voice via Kokoro TTS.\n"
            "Cadence: 1-2 spoken sentences maximum. Crisp, natural, and direct.\n"
            f"Anti-Repetition Rule: Avoid repeating these recent phrases: [{recent_str}]. Vary your vocabulary and sentence openings.\n"
        )
        return addon

    @staticmethod
    def strip_robotic_filler(text: str) -> str:
        """
        Strips corporate/robotic AI boilerplate ('As an AI', 'Certainly!', 'I'd be happy to help')
        so Libra always speaks like a natural, sharp human companion.
        """
        if not text:
            return ""
        cleaned = text.strip()
        # Strip leading filler phrases iteratively in any order
        leading_patterns = [
            r"^(?:certainly|sure\s+thing|absolutely|of\s+course)[\!\,\.]\s*(?:here\s+is\s+[^:\.]*[:\.]?\s*)?",
            r"^i(?:'d|\s+would)\s+be\s+(?:happy|glad|delighted)\s+to\s+help(?:\s+you\s+with\s+that)?[\!\,\.]\s*",
            r"^as\s+an\s+(?:ai|artificial\s+intelligence|language\s+model)[^,\.]*[,\.]\s*",
            r"^here\s+is\s+the\s+information\s+you\s+requested[:\.]\s*",
        ]
        changed = True
        while changed:
            changed = False
            for pat in leading_patterns:
                new_c = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
                if new_c != cleaned:
                    cleaned = new_c
                    changed = True

        # Strip trailing robotic sign-offs
        trailing_patterns = [
            r"\s*(?:let\s+me\s+know\s+if\s+you\s+need\s+anything\s+else|feel\s+free\s+to\s+ask\s+if\s+you\s+have\s+more\s+questions|i\s+hope\s+this\s+helps)[\!\.]*$",
        ]
        for pat in trailing_patterns:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()

        if cleaned and cleaned[0].islower():
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned or text.strip()

    def humanize_response(
        self,
        raw_response: str,
        action_type: str,
        context: Optional[Dict[str, Any]] = None,
        dry_run: bool = False
    ) -> str:
        """
        Transforms tool outputs into varied, natural spoken responses.
        Uses instant (<2ms) local phrasing pools parameterized with target/details
        and strictly avoids repeating any response present in self.recent_responses.
        """
        raw_response = self.strip_robotic_filler(raw_response or "")
        ctx = context or {}
        target = ctx.get("target") or ctx.get("app") or ctx.get("folder") or ctx.get("query") or ""

        # Dynamic variation pools for common tool actions
        pools: Dict[str, List[str]] = {
            "open_app": [
                f"Booting up {target}.",
                f"Launching {target} now.",
                f"{target} is coming right up.",
                f"Opening {target} for you.",
                f"Firing up {target}."
            ],
            "close_app": [
                f"Shutting down {target}.",
                f"Closed {target}.",
                f"Terminated {target} cleanly.",
                f"{target} has been closed.",
                f"{target} closed."
            ],
            "open_folder": [
                f"Revealed {target} in File Explorer.",
                f"Opening the {target} folder for you.",
                f"Brought up {target}.",
                f"Pulling up {target} now.",
                f"{target} is open on your screen."
            ],
            "spotify_play": [
                f"Playing {target} on Spotify." if target else "Playing music on Spotify.",
                f"Putting on {target} on Spotify now." if target else "Resuming your music.",
                f"Spinning {target} for you." if target else "Started Spotify playback.",
                f"Queued up {target} on Spotify." if target else "Spotify is playing.",
                f"{target} is now playing." if target else "Music online."
            ],
            "media_control": [
                "Adjusted playback.",
                "Handled.",
                "Media command executed.",
                "Track updated.",
                "Done."
            ],
            "launch_workspace": [
                f"Activating {target} workspace profile.",
                f"Switched over to {target} mode.",
                f"Environment configured for {target}.",
                f"{target.title()} setup is live.",
                f"Workspace transitioned to {target}."
            ],
            "remember_fact": [
                f"Committed to memory: {target}.",
                f"Noted. I will remember {target}.",
                f"Logged into neural memory: {target}.",
                f"Got it locked in: {target}."
            ],
            "create_skill": [
                f"Forged and loaded new skill: {target}.",
                f"Skill '{target}' synthesized and ready for deployment.",
                f"Learned skill '{target}'. It is now part of my active capabilities.",
                f"New capability '{target}' compiled and live."
            ],
            "system_status": [
                f"Current system status: {target}",
                f"Hardware vitals: {target}",
                f"System telemetry: {target}",
                f"Diagnostics report: {target}"
            ],
            "virus_scan": [
                f"Security scan complete: {target}",
                f"File safety assessment finished: {target}",
                f"Diagnostics complete: {target}"
            ],
            "show_ui": [
                "Displaying neural interface.",
                "Bringing up the interface now.",
                "Interface online and visible.",
                "Revealing UI."
            ],
            "hide_ui": [
                "Hiding interface. I'll remain active in the background.",
                "Minimizing to system tray.",
                "Interface hidden. I'm still listening in the background.",
                "Returning to background mode."
            ]
        }

        chosen = None

        if action_type in pools and (target or action_type in ["show_ui", "hide_ui", "media_control"]):
            candidates = pools[action_type]
            # Filter out responses that appear in recent responses
            unseen = [c for c in candidates if c not in self.recent_responses]
            if unseen:
                chosen = unseen[0]
            else:
                # If all have been seen recently, pick the one that appeared least recently
                recent_list = list(self.recent_responses)
                candidates_by_age = sorted(
                    candidates,
                    key=lambda c: recent_list.index(c) if c in recent_list else -1
                )
                chosen = candidates_by_age[0]
        else:
            # For unpooled or raw responses, check against repetition
            raw = (raw_response or "").strip()
            if raw in self.recent_responses:
                # Provide a slight conversational paraphrase prefix to avoid exact duplicate
                prefixes = ["As mentioned, ", "Just to confirm, ", "Right, "]
                for p in prefixes:
                    candidate = f"{p}{raw[0].lower() + raw[1:]}" if len(raw) > 1 else f"{p}{raw}"
                    if candidate not in self.recent_responses:
                        chosen = candidate
                        break
            if not chosen:
                chosen = raw

        # Record chosen in recent_responses
        if chosen:
            self.recent_responses.append(chosen)

        return chosen or raw_response

    def update_soul_trait(self, instruction: str) -> str:
        """
        Parses user personality instructions (e.g. 'Be more sarcastic', 'Talk more casually',
        'Be more concise') and persists them directly into assets/SOUL.md.
        """
        clean_inst = instruction.strip()

        # Extract core trait request
        trait_match = re.search(
            r"(?:be\s+more|talk\s+more|become\s+more|sound\s+more|switch\s+to|set\s+tone\s+to)\s+([a-zA-Z\s\-]+)",
            clean_inst,
            re.IGNORECASE
        )
        trait_value = trait_match.group(1).strip() if trait_match else clean_inst

        # Update in-memory soul document
        new_entry = f"- Dynamic Trait Update: {trait_value.capitalize()} (Requested: '{clean_inst}')\n"
        self.soul_content += f"\n{new_entry}"

        # Persist to disk
        try:
            os.makedirs(os.path.dirname(self.soul_path), exist_ok=True)
            with open(self.soul_path, "a", encoding="utf-8") as f:
                f.write(f"\n{new_entry}")
        except Exception as e:
            print(f"[PersonaEngine SOUL Persist Warning]: {e}")

        # Humanized acknowledgment
        ack_phrases = [
            f"Understood. Adjusted my behavioral parameters to be more {trait_value}.",
            f"Got it. Tone recalibrated: more {trait_value} going forward.",
            f"Parameters updated. I'll keep things {trait_value} from here on.",
            f"Soul matrix tuned. Expect a more {trait_value} demeanor."
        ]
        unseen = [a for a in ack_phrases if a not in self.recent_responses]
        chosen_ack = unseen[0] if unseen else ack_phrases[0]
        self.recent_responses.append(chosen_ack)
        return chosen_ack
