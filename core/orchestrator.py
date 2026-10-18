import os
import re
from typing import List, Dict, Any, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

from core.llm import LocalLLM
from core.text_cleaner import normalize_for_tts


ACTION_CLAUSE_PATTERNS = [
    r"\bremind\s+me\b",
    r"\bremember\s+(?:that\s+)?\b",
    r"\bforget\b",
    r"\b(?:launch|open|start|run|play)\s+(?:[a-zA-Z0-9_\-]+)\b",
    r"\b(?:close|shut\s*down|exit|kill)\b",
    r"\b(?:system\s+status|cpu|ram|gpu|hardware|windows|diagnostics?)\b",
    r"\b(?:find|search\s+for|look\s+for)\s+(?:bookstores|cafes|restaurants|places|coffee)\b",
    r"\bset\s+a\s+timer\b",
    r"\b(?:create|make)\s+(?:a\s+)?(?:new\s+)?folder\b",
    r"\b(?:open|show|reveal|find)\s+(?:the\s+|that\s+)?[a-zA-Z0-9_\-\s]+\s+(?:folder|on\s+here|in\s+file\s+explorer)\b",
    r"\b(?:enable|turn\s+on|activate|disable|turn\s+off|exit)\s+game\s+mode\b",
    r"\b(?:deep\s+research|heavy\s+research|think\s+deeply|analyze\s+in\s+depth)\b",
    r"\b(?:look\s+at|what\s+is\s+on|read\s+the\s+error\s+on)\s+my\s+screen\b",
    r"\b(?:clipboard|what\s+i\s+copied)\b",
    r"\b(?:read|analyze|search\s+in)\s+my\s+[a-zA-Z0-9_\-\s]+(?:\.pdf|\.docx|\.txt|\.py|\.md)?\b",
    r"\b(?:switch\s+to|set\s+up|activate|prepare\s+for|start|launch)\s+(?:coding|study|gaming)\s+(?:mode|workspace)\b",
    r"\b(?:pause|resume|skip|next\s+song|previous\s+song|volume\s+up|volume\s+down|lower\s+(?:the\s+)?volume|mute)\b",
    r"\b(?:virus\s+scan|malware\s+scan|security\s+scan|scan\s+.*?\s+for\s+viruses|check\s+if\s+.*?\s+is\s+safe)\b",
    r"\b(?:play|listen\s+to)\s+.*?\s*on\s+spotify\b",
    r"\b(?:what\s+is\s+inside|what(?:'s|\s+is)\s+in)\s+(?:this\s+|the\s+)?(?:file|document|readme)\b",
    r"\b(?:explain|summarize|read|tell\s+me\s+about)\s+(?:to\s+\w+\s+)?(?:what\s+is\s+inside|this\s+file|the\s+file|the\s+document|this\s+document|readme|the\s+readme)\b",
    r"\b(?:summarize|explain)\s+(?:the\s+|this\s+)?(?:file|document|pdf|readme)\b",
    r"\b(?:explain\s+to\s+\w+|what\s+is\s+inside\s+this\s+file)\b",
    r"\b(?:create|learn|build|teach\s+yourself|save)\s+(?:a\s+)?(?:new\s+)?skill\b",
    r"\b(?:what\s+skills\s+do\s+you\s+have|list\s+(?:your\s+)?skills|show\s+skills)\b",
    r"\b(?:be\s+more|talk\s+more|sound\s+more|switch\s+to|set\s+tone\s+to)\b",
    r"\b(?:change\s+your\s+personality|update\s+your\s+soul)\b",
    r"\b(?:morning|daily|boot)\s+briefing\b",
    r"\bgood\s+morning\b",
    r"\bstatus\s+report\b",
    r"\b(?:find\s+(?:me\s+)?(?:valid\s+)?data\s+(?:on|about|for)|analyze\s+(?:the\s+)?dataset|make\s+(?:it\s+into\s+)?a\s+visualization|generate\s+a\s+(?:plot|chart|visualization))\b",
    r"\b(?:weather|forecast|temperature|is\s+it\s+going\s+to\s+rain|how\s+hot\s+is\s+it)\b",
    r"\b(?:check\s+my\s+ping|what\s+time\s+is\s+it|convert\s+\d+|how\s+much\s+is\s+\d+|how\s+far\s+is)\b",
    r"\b(?:what\s+am\s+i\s+working\s+on|what\s+window\s+am\s+i\s+in|what\s+does\s+this\s+error\s+mean|explain\s+what\s+this\s+script\s+does|summarize\s+what(?:'s|\s+is)\s+on\s+this\s+page|write\s+a\s+reply\s+to\s+this)\b",
    r"\b(?:what\s+song\s+is\s+playing|what(?:'s|\s+is)\s+playing\s+on\s+spotify|list\s+my\s+reminders|cancel\s+my\s+reminders|wake\s+me\s+up)\b",
    r"\b(?:show|open|bring\s+up|display)\s+(?:me\s+)?(?:your\s+|the\s+)?(?:neural\s+)?(?:ui|window|interface)\b",
    r"\b(?:hide|close|minimize)\s+(?:me\s+)?(?:your\s+)?(?:neural\s+)?(?:ui|window|interface)\b",
    r"\b(?:go\s+to\s+background|send\s+to\s+background|hide\s+window|minimize\s+window|minimize\s+ui)\b"
]


class SupervisorHub:
    """
    Central Multi-Agent Supervisor Hub for Project Libra.
    Supports sub-5ms fast-path bypass for single-intent requests and an ordered,
    strictly capped multi-step execution queue (MAX_STEPS = 4) for compound voice commands.
    """

    MAX_STEPS: int = 4

    def __init__(self, llm: Optional[LocalLLM] = None):
        self.llm = llm if llm is not None else LocalLLM()
        self.scratchpad = self.llm.scratchpad
        self.clarifier = self.llm.clarifier
        self.refiner = self.llm.refiner
        self.sentiment = self.llm.sentiment
        self.distiller = self.llm.distiller
        self.artifacts = self.llm.artifacts
        self.data_scientist = self.llm.data_scientist
        self.utility_belt = self.llm.utility_belt
        self.window_engine = self.llm.window_engine
        self.idle_daemon = self.llm.idle_daemon

    @property
    def attached_file_path(self) -> Optional[str]:
        return getattr(self.llm, "attached_file_path", None)

    @attached_file_path.setter
    def attached_file_path(self, path: Optional[str]):
        if self.llm:
            self.llm.attached_file_path = path

    def is_action_clause(self, text: str) -> bool:
        """Determines if a clause contains a known actionable intent keyword."""
        return any(re.search(pat, text, re.IGNORECASE) for pat in ACTION_CLAUSE_PATTERNS)

    def split_compound_intent(self, prompt: str) -> List[str]:
        """
        Splits compound requests into sequential sub-intents while preserving
        single complex requests (e.g., explicit web searches, relative clauses).
        Capped at MAX_STEPS (4).
        """
        # Preserve explicit compound web search idioms, Spotify play idioms, and unified data science requests
        if re.search(r"open\s+(?:google|chrome|browser)\s+and\s+search", prompt, re.IGNORECASE):
            return [prompt]
        if re.search(r"\b(?:open|launch|start|play)\s+(?:my\s+)?spotify\s+(?:and|to)\s+(?:play|place)\b", prompt, re.IGNORECASE):
            return [prompt]
        if re.search(r"\b(?:find\s+(?:me\s+)?(?:valid\s+)?data\s+(?:on|about|for)|analyze\s+(?:the\s+)?dataset|make\s+(?:it\s+into\s+)?a\s+visualization)\b", prompt, re.IGNORECASE):
            return [prompt]

        # Sequencing delimiters: 'and then', 'then', ', and', 'and', ';'
        split_regex = r"\s+(?:,\s*and\s+then|;\s*|then|and\s+then|,\s*and|and)\s+"
        parts = re.split(split_regex, prompt, flags=re.IGNORECASE)
        cleaned_parts = [p.strip() for p in parts if p.strip()]

        if len(cleaned_parts) <= 1:
            return [prompt]

        # Only treat as compound if at least 2 clauses are actionable intents
        actionable_count = sum(1 for p in cleaned_parts if self.is_action_clause(p))
        if actionable_count >= 2:
            return cleaned_parts[:self.MAX_STEPS]

        return [prompt]

    def plan_or_execute(self, prompt: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Executes the prompt through either fast-path single dispatch or multi-step coordination
        backed by AgentScratchpad.
        """
        sub_steps = self.split_compound_intent(prompt)

        # FAST PATH (<5ms): Single intent query
        if len(sub_steps) == 1:
            res = self.llm.plan(prompt, dry_run=dry_run)
            res["compound"] = False
            return res

        # MULTI-STEP COMPOUND PIPELINE (Max 4 steps via AgentScratchpad)
        initial_subtasks = [
            {"id": idx + 1, "action": step, "args": {"prompt": step}, "status": "pending", "result": None}
            for idx, step in enumerate(sub_steps[:self.MAX_STEPS])
        ]
        self.scratchpad.init_plan(goal=prompt, subtasks=initial_subtasks)

        step_results: List[Dict[str, Any]] = []
        voice_responses: List[str] = []

        for idx, step in enumerate(sub_steps[:self.MAX_STEPS]):
            if idx < len(self.scratchpad.subtasks):
                self.scratchpad.subtasks[idx]["status"] = "running"
            res = self.llm.plan(step, dry_run=dry_run)
            if idx < len(self.scratchpad.subtasks):
                self.scratchpad.subtasks[idx]["action"] = res.get("action", step)
                self.scratchpad.subtasks[idx]["args"] = res.get("args", {})
            self.scratchpad.reflect_and_plan(res)
            step_results.append(res)
            v = res.get("voice_response")
            if v and v != "Dry-run response.":
                voice_responses.append(v)

        actions = [r.get("action") for r in step_results]

        if voice_responses:
            combined_voice = " ".join(voice_responses)
            combined_voice = normalize_for_tts(combined_voice)
        else:
            combined_voice = self.scratchpad.compress_for_speech()

        return {
            "compound": True,
            "steps": sub_steps[:self.MAX_STEPS],
            "actions": actions,
            "step_results": step_results,
            "scratchpad": self.scratchpad.get_state(),
            "voice_response": combined_voice
        }

    def plan(self, prompt: str) -> Dict[str, Any]:
        """Dry-run planner isolating side-effects."""
        return self.plan_or_execute(prompt, dry_run=True)

    def execute(self, prompt: str) -> Dict[str, Any]:
        """Live execution pipeline."""
        return self.plan_or_execute(prompt, dry_run=False)
