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
    r"\b(?:morning|daily|boot)\s+briefing\b",
    r"\bgood\s+morning\b",
    r"\bstatus\s+report\b"
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

    def is_action_clause(self, text: str) -> bool:
        """Determines if a clause contains a known actionable intent keyword."""
        return any(re.search(pat, text, re.IGNORECASE) for pat in ACTION_CLAUSE_PATTERNS)

    def split_compound_intent(self, prompt: str) -> List[str]:
        """
        Splits compound requests into sequential sub-intents while preserving
        single complex requests (e.g., explicit web searches, relative clauses).
        Capped at MAX_STEPS (4).
        """
        # Preserve explicit compound web search idioms
        if re.search(r"open\s+(?:google|chrome|browser)\s+and\s+search", prompt, re.IGNORECASE):
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
        Executes the prompt through either fast-path single dispatch or multi-step coordination.
        """
        sub_steps = self.split_compound_intent(prompt)

        # FAST PATH (<5ms): Single intent query
        if len(sub_steps) == 1:
            res = self.llm.plan(prompt, dry_run=dry_run)
            res["compound"] = False
            return res

        # MULTI-STEP COMPOUND PIPELINE (Max 4 steps)
        step_results: List[Dict[str, Any]] = []
        voice_responses: List[str] = []

        for step in sub_steps:
            res = self.llm.plan(step, dry_run=dry_run)
            step_results.append(res)
            v = res.get("voice_response")
            if v:
                voice_responses.append(v)

        actions = [r.get("action") for r in step_results]

        if voice_responses:
            combined_voice = " ".join(voice_responses)
            combined_voice = normalize_for_tts(combined_voice)
        else:
            combined_voice = f"Completed {len(step_results)} actions: " + ", ".join(filter(None, actions)) + "."

        return {
            "compound": True,
            "steps": sub_steps,
            "actions": actions,
            "step_results": step_results,
            "voice_response": combined_voice
        }

    def plan(self, prompt: str) -> Dict[str, Any]:
        """Dry-run planner isolating side-effects."""
        return self.plan_or_execute(prompt, dry_run=True)

    def execute(self, prompt: str) -> Dict[str, Any]:
        """Live execution pipeline."""
        return self.plan_or_execute(prompt, dry_run=False)
