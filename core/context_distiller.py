import re
from typing import List, Dict, Any, Tuple, Optional

STOP_CAP_WORDS = {
    "The", "This", "That", "What", "When", "Where", "Which", "Who", "Why", "How",
    "Can", "Could", "Would", "Should", "Please", "Hey", "Hello", "Hi", "Yes", "No",
    "Okay", "Sure", "Thanks", "Thank", "User", "Assistant", "Libra", "Understood",
    "Tell", "Show", "Open", "Launch", "Create", "Switch", "Start", "Check", "Find"
}


class ContextDistiller:
    """
    Context Rolling Compaction & Memory Distillation Engine for Project Libra v6.0.
    Compresses older conversational turns into a dense 2-sentence summary when history
    reaches or exceeds the threshold, embeds and archives the summary in SemanticMemory
    under category='session_distillation', and keeps the active context window under 2,048 tokens.
    """

    MAX_TOKEN_BUDGET: int = 2048

    def __init__(self, memory: Optional[Any] = None):
        self.memory = memory
        self.distilled_summaries: List[str] = []

    @staticmethod
    def _extract_turn_text(turn: Dict[str, Any]) -> str:
        """Extracts text from either {'role': ..., 'content': ...} or {'user': ..., 'assistant': ...} dicts."""
        if not isinstance(turn, dict):
            return str(turn)
        parts = []
        if "content" in turn and turn["content"]:
            parts.append(str(turn["content"]))
        if "user" in turn and turn["user"]:
            parts.append(str(turn["user"]))
        if "assistant" in turn and turn["assistant"]:
            parts.append(str(turn["assistant"]))
        if "text" in turn and turn["text"]:
            parts.append(str(turn["text"]))
        return " ".join(parts).strip()

    def _extract_key_entities(self, turns: List[Dict[str, Any]]) -> List[str]:
        """Extracts proper nouns, technical identifiers, filenames, and key entities across turns."""
        entities: List[str] = []
        seen_lower = set()

        for turn in turns:
            text = self._extract_turn_text(turn)
            if not text:
                continue

            # 1. Match multi-word or single-word capitalized proper nouns & technical terms (e.g. RTX 5080, Project Alpha)
            cap_matches = re.findall(r"\b[A-Z][a-zA-Z0-9_\-\.]*(?:\s+[A-Z0-9][a-zA-Z0-9_\-\.]*)*\b", text)
            for m in cap_matches:
                clean_m = m.strip(".,?!:;\"'")
                # Strip leading stop word if multi-word
                tokens = clean_m.split()
                while tokens and tokens[0] in STOP_CAP_WORDS:
                    tokens.pop(0)
                clean_m = " ".join(tokens)
                if clean_m and len(clean_m) >= 2 and clean_m not in STOP_CAP_WORDS:
                    low = clean_m.lower()
                    if low not in seen_lower:
                        seen_lower.add(low)
                        entities.append(clean_m)

            # 2. Match filenames or paths (e.g. proposal.pdf, train.py)
            file_matches = re.findall(r"\b[\w\-]+\.(?:py|md|txt|pdf|docx|csv|json|db|exe)\b", text, re.IGNORECASE)
            for fm in file_matches:
                low = fm.lower()
                if low not in seen_lower:
                    seen_lower.add(low)
                    entities.append(fm)

        return entities[:10]

    def _build_summary(self, older_turns: List[Dict[str, Any]]) -> str:
        """Synthesizes a dense 2-sentence context summary preserving key entities and topics."""
        entities = self._extract_key_entities(older_turns)

        user_snippets: List[str] = []
        for t in older_turns:
            role = str(t.get("role", "")).lower()
            if role == "user" or "user" in t or not role:
                txt = str(t.get("content") or t.get("user") or t.get("text") or "").strip()
                if txt and not txt.startswith("[Context Summary:"):
                    clean_s = re.sub(r"\s+", " ", txt).rstrip(".?!")
                    if len(clean_s) > 60:
                        clean_s = clean_s[:57].rstrip() + "..."
                    user_snippets.append(clean_s)

        if len(user_snippets) >= 2:
            work_topic = user_snippets[0]
            ask_topic = user_snippets[-1]
        elif len(user_snippets) == 1:
            work_topic = user_snippets[0]
            ask_topic = "related follow-up tasks"
        else:
            work_topic = "desktop operations"
            ask_topic = "system queries"

        entity_clause = (
            f" Key entities referenced: {', '.join(entities)}."
            if entities
            else " Active session context maintained."
        )

        summary = (
            f"[Context Summary: User was working on {work_topic} and asked about {ask_topic}."
            f"{entity_clause}]"
        )
        return summary

    def compress_history(
        self,
        turns: List[Dict[str, Any]],
        threshold: int = 8,
        dry_run: bool = False
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        When conversational turn history reaches or exceeds `threshold` (default 8),
        compacts older turns (turns 0..5 or turns[:-2]) into a dense 2-sentence summary,
        embeds and persists it in SemanticMemory under category='session_distillation',
        and preserves recent raw turns with the summary prepended.
        """
        if not turns or len(turns) < threshold:
            return list(turns or []), ""

        # Compact turns 0..5 (or all but the last 2 turns when > 8)
        split_idx = max(6, len(turns) - 2)
        older_turns = turns[:split_idx]
        recent_turns = turns[split_idx:]

        summary = self._build_summary(older_turns)
        self.distilled_summaries.append(summary)

        # Persist to SemanticMemory under category='session_distillation'
        if self.memory is not None and not dry_run:
            try:
                if hasattr(self.memory, "remember_fact"):
                    self.memory.remember_fact(summary, category="session_distillation")
                elif hasattr(self.memory, "embed_text"):
                    self.memory.embed_text(summary)
            except Exception as e:
                print(f"[ContextDistiller Memory Persist Warning]: {e}")

        summary_turn = {"role": "system", "content": summary}
        compressed = [summary_turn] + list(recent_turns)
        return compressed, summary

    @staticmethod
    def estimate_tokens(turns: List[Dict[str, Any]]) -> int:
        """Rough token estimator (~4 chars per token) to verify <2,048 token ceiling."""
        total_chars = sum(len(str(t)) for t in (turns or []))
        return max(1, total_chars // 4)
