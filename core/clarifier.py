import os
import re
from typing import Dict, Any, Optional, List


ORDINAL_MAP = {
    "first": 0,
    "1st": 0,
    "one": 0,
    "number 1": 0,
    "number one": 0,
    "option 1": 0,
    "option one": 0,
    "#1": 0,
    "second": 1,
    "2nd": 1,
    "two": 1,
    "number 2": 1,
    "number two": 1,
    "option 2": 1,
    "option two": 1,
    "#2": 1,
    "third": 2,
    "3rd": 2,
    "three": 2,
    "number 3": 2,
    "number three": 2,
    "option 3": 2,
    "option three": 2,
    "#3": 2,
}

GENERIC_TARGETS = {
    "",
    "project",
    "the project",
    "my project",
    "project folder",
    "the project folder",
    "my project folder",
    "folder",
    "the folder",
    "that folder",
    "file",
    "the file",
    "my file",
    "notes",
    "the notes",
    "my notes",
    "document",
    "the document",
    "my document",
    "app",
    "the app",
}


class AmbiguityDetector:
    """
    Active Clarification & Ambiguity Detector for Project Libra v6.0.
    Detects underspecified or multi-candidate intents, asks concise clarifying questions
    with 2-3 named options, and resolves ordinal or short name replies on the next turn.
    """

    def __init__(self):
        pass

    @staticmethod
    def _extract_option_name(item: Any) -> str:
        """Extracts a clean human-readable name from a candidate dict or path string."""
        if isinstance(item, dict):
            for key in ("name", "title", "folder", "label", "app_id"):
                if item.get(key):
                    return str(item[key]).strip()
            if item.get("path"):
                p = str(item["path"]).rstrip("\\/")
                return os.path.basename(p) or p
            return str(item)
        if isinstance(item, str):
            clean = item.strip().rstrip("\\/")
            if "\\" in clean or "/" in clean:
                return os.path.basename(clean) or clean
            return clean
        return str(item)

    @staticmethod
    def _extract_option_path(item: Any) -> Optional[str]:
        """Extracts filesystem path from candidate if available."""
        if isinstance(item, dict):
            return item.get("path")
        if isinstance(item, str) and ("\\" in item or "/" in item or os.path.exists(item)):
            return item
        return None

    def check_ambiguity(
        self,
        intent: str,
        args: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates whether an intent is ambiguous given its arguments and current session/disk context.
        If ambiguous, returns a structured clarification payload with 2-3 named options and a polite question.
        Otherwise returns None.
        """
        args_dict = dict(args or {})
        ctx = dict(context or {})

        raw_target = (
            args_dict.get("folder")
            or args_dict.get("target")
            or args_dict.get("file")
            or args_dict.get("app_id")
            or args_dict.get("query")
            or ""
        )
        target_clean = str(raw_target).strip()
        target_lower = target_clean.lower()

        candidates: List[Any] = (
            ctx.get("candidates")
            or ctx.get("matches")
            or ctx.get("options")
            or []
        )

        # Filter candidates if target is a non-generic partial string
        is_generic = (
            target_lower in GENERIC_TARGETS
            or bool(re.match(r"^(?:the\s+|my\s+|a\s+)?(?:project|folder|file|notes?|documents?)(?:\s+folder|\s+file)?$", target_lower))
        )

        matched_candidates: List[Any] = []
        if is_generic:
            matched_candidates = list(candidates)
        elif candidates and target_lower:
            for c in candidates:
                c_name = self._extract_option_name(c).lower()
                if target_lower in c_name or c_name in target_lower:
                    matched_candidates.append(c)

        # Ambiguity condition: 2+ candidates match, OR target is completely missing on a target-required action
        target_required_intents = {
            "open_folder", "delete_file", "open_file", "document_rag", "show_notes", "open_app"
        }

        if len(matched_candidates) >= 2:
            top_options = matched_candidates[:3]
            option_names = [self._extract_option_name(c) for c in top_options]
            ambiguity_score = min(0.95, 0.70 + 0.08 * len(matched_candidates))

            if "folder" in intent.lower() or "folder" in target_lower:
                noun = "folders"
            elif "file" in intent.lower() or "document" in intent.lower() or "file" in target_lower:
                noun = "files"
            elif "note" in intent.lower() or "note" in target_lower:
                noun = "notes"
            else:
                noun = "options"

            if len(option_names) == 2:
                question = f"I found two matching {noun}: {option_names[0]} and {option_names[1]}. Which one did you mean?"
            else:
                question = (
                    f"I found {len(option_names)} matching {noun}: "
                    f"{', '.join(option_names[:-1])}, and {option_names[-1]}. Which one did you mean?"
                )

            return {
                "is_ambiguous": True,
                "ambiguity_score": round(ambiguity_score, 2),
                "intent": intent,
                "args": args_dict,
                "options": top_options,
                "option_names": option_names,
                "question": question,
                "voice_response": question
            }

        if intent in target_required_intents and is_generic and not matched_candidates:
            question = f"Which specific {target_lower or 'item'} would you like me to {intent.replace('_', ' ')}?"
            return {
                "is_ambiguous": True,
                "ambiguity_score": 0.90,
                "intent": intent,
                "args": args_dict,
                "options": [],
                "option_names": [],
                "question": question,
                "voice_response": question
            }

        return None

    def resolve_clarification(
        self,
        user_reply: str,
        pending_state: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Resolves a user's follow-up turn (e.g., 'the first one', 'second', 'LibraAi')
        against the pending clarification state.
        """
        if not pending_state or not user_reply:
            return None

        reply_clean = user_reply.strip()
        reply_lower = reply_clean.lower().rstrip(".?!")
        options: List[Any] = pending_state.get("options") or []
        option_names: List[str] = pending_state.get("option_names") or [
            self._extract_option_name(o) for o in options
        ]
        intent = pending_state.get("intent", "open_folder")
        orig_args = dict(pending_state.get("args") or {})

        selected_idx: Optional[int] = None

        # 1. Check ordinal phrases ('the first one', '1st', 'number 2', 'last one')
        if re.search(r"\blast(?:\s+one|\s+option|\s+folder|\s+file)?\b", reply_lower) and options:
            selected_idx = len(options) - 1
        else:
            for phrase, idx in ORDINAL_MAP.items():
                if re.search(rf"\b{re.escape(phrase)}\b", reply_lower):
                    if idx < len(options):
                        selected_idx = idx
                        break

        # 2. Check direct or partial name match ('Libra', 'LibraAi', 'SimpleClimate')
        if selected_idx is None and option_names:
            # Strip conversational filler
            stripped_reply = re.sub(
                r"^(?:i\s+meant|i\s+mean|open|select|choose|pick|the|folder|file|option)\s+",
                "",
                reply_lower
            ).strip()
            for idx, name in enumerate(option_names):
                name_lower = name.lower()
                if (
                    stripped_reply == name_lower
                    or reply_lower in name_lower
                    or name_lower in reply_lower
                    or (len(stripped_reply) >= 3 and stripped_reply in name_lower)
                ):
                    selected_idx = idx
                    break

        if selected_idx is None and not options and reply_clean:
            # Open-ended clarification where no predefined options existed
            chosen_name = reply_clean.rstrip(".?!")
            chosen_option = chosen_name
        elif selected_idx is not None and 0 <= selected_idx < len(options):
            chosen_option = options[selected_idx]
            chosen_name = option_names[selected_idx]
        else:
            return None

        updated_args = dict(orig_args)
        opt_path = self._extract_option_path(chosen_option)
        if intent == "open_folder" or "folder" in updated_args:
            updated_args["folder"] = chosen_name
            if opt_path:
                updated_args["path"] = opt_path
        elif intent in ["document_rag", "open_file", "delete_file"] or "file" in updated_args:
            updated_args["file"] = opt_path or chosen_name
        elif intent == "open_app" or "app_id" in updated_args:
            updated_args["app_id"] = chosen_name
            updated_args["target_app"] = chosen_name
        else:
            updated_args["target"] = chosen_name

        return {
            "resolved": True,
            "intent": intent,
            "selected": chosen_option,
            "selected_name": chosen_name,
            "args": updated_args
        }
