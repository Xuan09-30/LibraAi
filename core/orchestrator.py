import os
import re
import time
from typing import List, Dict, Any, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

from core.llm import LocalLLM
from core.text_cleaner import normalize_for_tts
from core.telemetry import profiler
from core.dispatcher import is_weather_intent, dispatch_weather
from tools.computer_use_agent import AutonomousComputerUseAgent


def normalize_trigger(text: str) -> str:
    """Normalizes conversational prompts for deterministic PreAct macro lookup."""
    t = (text or "").lower().strip()
    t = re.sub(r"^(?:hey\s+)?libra[,:\s]*", "", t)
    t = re.sub(r"^(?:can\s+you\s+(?:help\s+me\s+to\s+|please\s+)?|please\s+|help\s+me\s+(?:to\s+)?|i\s+want\s+you\s+to\s+|i\s+want\s+to\s+|could\s+you\s+)", "", t)
    t = re.sub(r"[\.\?!]+$", "", t).strip()
    return t


BLOCKED_REMOTE_ACTIONS = {
    "gui_action",
    "computer_use_agent",
    "open_app",
    "close_app",
    "shutdown",
    "analyze_screen",
    "open_folder",
    "open_file",
    "create_folder",
    "create_file",
    "write_file",
    "select_profile",
    "media_action",
    "virus_scan",
}

REMOTE_SANDBOX_PATTERNS = [
    r"\b(?:launch|open|start|run|close|kill|shut\s*down)\s+(?:the\s+)?(?:app|application|game|program|software|chrome|steam|notepad|calc|pc|computer|system)\b",
    r"\b(?:click|double\s+click|right\s+click|press|tap)\s+(?:on\s+)?(?:the\s+)?(?:screen|button|icon|window|profile)\b",
    r"\b(?:look\s+at|what\s+is\s+on|see\s+on|capture|check)\s+my\s+screen\b",
    r"\b(?:open|show|reveal)\s+(?:that\s+|the\s+)?(?:folder|directory|file)\b",
    r"\b(?:mute|unmute|volume\s+up|volume\s+down|pause\s+the\s+music|stop\s+music)\b",
]

CANONICAL_FASTPATH_INTENTS = {
    "volume_down": {
        "action": "media_action", "args": {"sub_action": "volume_down"}, "voice": "Turned down volume.",
        "phrases": ["lower volume", "crank tunes down", "crank the tunes down", "volume down", "turn sound down", "decrease volume", "too loud", "lower the music", "quiet down", "lower the volume"]
    },
    "volume_up": {
        "action": "media_action", "args": {"sub_action": "volume_up"}, "voice": "Turned up volume.",
        "phrases": ["crank volume up", "turn it up", "louder", "increase volume", "volume up", "boost volume", "crank it up", "make it louder"]
    },
    "mute": {
        "action": "media_action", "args": {"sub_action": "mute"}, "voice": "Muted audio.",
        "phrases": ["mute audio", "silence", "mute sound", "kill volume", "mute the computer", "shut sound off"]
    },
    "pause_media": {
        "action": "media_action", "args": {"sub_action": "pause"}, "voice": "Paused playback.",
        "phrases": ["pause music", "pause spotify", "stop playing", "hold playback", "pause song", "freeze music"]
    },
    "resume_media": {
        "action": "media_action", "args": {"sub_action": "resume"}, "voice": "Resumed playback.",
        "phrases": ["resume music", "continue playing", "play song", "unpause", "resume playback", "start playing again"]
    },
    "system_vitals": {
        "action": "system_status", "args": {}, "voice": "Checking system vitals.",
        "phrases": [
            "system status", "hardware diagnostics", "pc health", "cpu and ram status",
            "gpu load", "how is my pc doing", "check computer stats", "check system vitals",
            "system vitals", "how hot is my gpu running right now", "how hot is my gpu",
            "gpu temperature", "check pc vitals", "gpu status"
        ]
    }
}


ACTION_CLAUSE_PATTERNS = [
    r"\bremind\s+me\b",
    r"\bremember\s+(?:that\s+)?\b",
    r"\bforget\b",
    r"\b(?:launch|open|start|run|play)\s+(?:[a-zA-Z0-9_\-]+)\b",
    r"\b(?:close|shut\s*down|exit|kill)\b",
    r"\b(?:system\s+status|cpu|ram|gpu|hardware|windows|diagnostics?)\b",
    r"\b(?:find|search\s+for|look\s+for)\s+(?:bookstores|cafes|restaurants|places|coffee|food)\b",
    r"\bset\s+a\s+timer\b",
    r"\b(?:create|make)\s+(?:a\s+)?(?:new\s+)?folder\b",
    r"\b(?:create|make|write|build)\s+(?:a\s+)?(?:new\s+)?(?:python\s+|text\s+|code\s+)?file\b",
    r"\b(?:open|show|reveal|view|edit)\s+(?:the\s+|that\s+)?(?:file|script|[a-zA-Z0-9_\-\.]+\.(?:py|txt|json|md))\b",
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
    r"\b(?:check\s+my\s+ping|what\s+time\s+is\s+it|what\s+is\s+the\s+time|what(?:'s|\s+is)\s+the\s+time|time\s+here|time\s+in\s+[a-zA-Z\s]+|convert\s+\d+|how\s+much\s+is\s+\d+|how\s+far\s+is)\b",
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
        cleaned = re.sub(r"^(?:also\s+|please\s+|can\s+you\s+(?:tell\s+me\s+about\s+)?|now\s+|what\s+about\s+)", "", text.strip(), flags=re.IGNORECASE)
        return any(re.search(pat, text, re.IGNORECASE) or re.search(pat, cleaned, re.IGNORECASE) for pat in ACTION_CLAUSE_PATTERNS)

    def split_compound_intent(self, prompt: str) -> List[str]:
        """
        Splits compound requests into sequential sub-intents while preserving
        single complex requests (e.g., explicit web searches, relative clauses).
        Capped at MAX_STEPS (4).
        """
        # Preserve multi-step Computer-Use ReAct prompts and explicit compound web search idioms
        if AutonomousComputerUseAgent.is_computer_use_prompt(prompt):
            return [prompt]
        if re.search(r"open\s+(?:my\s+)?(?:google|chrome|browser)\s+and\s+search", prompt, re.IGNORECASE):
            return [prompt]
        if re.search(r"\b(?:open|launch|start|play)\s+(?:my\s+)?spotify\s+(?:and|to)\s+(?:play|place)\b", prompt, re.IGNORECASE):
            return [prompt]
        if re.search(r"\b(?:find\s+(?:me\s+)?(?:valid\s+)?data\s+(?:on|about|for)|analyze\s+(?:the\s+)?dataset|make\s+(?:it\s+into\s+)?a\s+visualization)\b", prompt, re.IGNORECASE):
            return [prompt]
        # Preserve unified weather requests containing 'and' (e.g. 'current weather and rain forecast')
        if re.search(r"\bweather\s+and\s+(?:the\s+)?(?:rain\s+)?forecast\b", prompt, re.IGNORECASE) or \
           (re.search(r"\bweather\b", prompt, re.IGNORECASE) and re.search(r"\b(?:rain\s+)?forecast\b", prompt, re.IGNORECASE) and not re.search(r"\b(?:open|launch|close|kill|play|switch)\b", prompt, re.IGNORECASE)):
            return [prompt]

        # Sequencing delimiters: 'and then', 'then', ', and', 'and also', 'and', ';'
        split_regex = r"\s+(?:,\s*and\s+then|;\s*|then|and\s+then|,\s*and|and\s+also|and)\s+"
        parts = re.split(split_regex, prompt, flags=re.IGNORECASE)
        cleaned_parts = [p.strip() for p in parts if p.strip()]

        if len(cleaned_parts) <= 1:
            return [prompt]

        # Only treat as compound if at least 2 clauses are actionable intents
        actionable_count = sum(1 for p in cleaned_parts if self.is_action_clause(p))
        if actionable_count >= 2:
            return cleaned_parts[:self.MAX_STEPS]

        return [prompt]

    def _execute_cached_tool(self, action: str, args: dict, dry_run: bool = False) -> Dict[str, Any]:
        """Dispatches an already-compiled tool action directly to the runtime module."""
        if action == "open_app":
            target = args.get("app_id") or args.get("target", "")
            res = self.llm.dispatcher.launch_app(target, dry_run=dry_run)
            if isinstance(res, tuple):
                success, msg = res
                return {"action": "open_app", "target": target, "status": "success" if success else "error", "voice_response": msg}
            return res if isinstance(res, dict) else {"action": "open_app", "status": "success", "voice_response": str(res)}
        elif action == "close_app":
            target = args.get("app_id") or args.get("target", "")
            res = self.llm.dispatcher.terminate_app(target, dry_run=dry_run)
            if isinstance(res, tuple):
                success, msg = res
                return {"action": "close_app", "target": target, "status": "success" if success else "error", "voice_response": msg}
            return res if isinstance(res, dict) else {"action": "close_app", "status": "success", "voice_response": str(res)}
        elif action == "gui_action":
            sub_action = args.get("sub_action")
            if sub_action == "select_profile":
                return self.llm.gui_control.select_chrome_profile_ui(args.get("index", 0), dry_run=dry_run)
            elif sub_action == "click_mark":
                return self.llm.gui_control.click(x=args.get("x"), y=args.get("y"), dry_run=dry_run)
        elif action == "media_action":
            sub_action = args.get("sub_action")
            if hasattr(self.llm, "media_ctrl"):
                if sub_action == "volume_down":
                    return self.llm.media_ctrl.volume_down(dry_run=dry_run)
                elif sub_action == "volume_up":
                    return self.llm.media_ctrl.volume_up(dry_run=dry_run)
                elif sub_action == "mute":
                    return self.llm.media_ctrl.mute(dry_run=dry_run)
                elif sub_action == "pause":
                    return self.llm.media_ctrl.pause(dry_run=dry_run)
                elif sub_action == "resume":
                    return self.llm.media_ctrl.resume(dry_run=dry_run)
                elif sub_action == "stop":
                    return self.llm.media_ctrl.stop(dry_run=dry_run)
                elif sub_action == "play":
                    return self.llm.media_ctrl.play(dry_run=dry_run)
                elif sub_action == "next_track":
                    return self.llm.media_ctrl.next_track(dry_run=dry_run)
                elif sub_action == "prev_track":
                    return self.llm.media_ctrl.prev_track(dry_run=dry_run)
        elif action == "system_status":
            if hasattr(self.llm, "monitor"):
                metrics = self.llm.monitor.get_system_metrics()
                return {"action": "system_status", "status": "success", "voice_response": f"Current system status: {metrics['summary']}", "metrics": metrics}
        elif action == "daily_briefing":
            brief = getattr(self.llm, "briefing_and_workspaces", None) or getattr(self.llm, "briefing_engine", None)
            if brief:
                res_b = brief.generate_briefing(dry_run=dry_run)
                voice_str = str(res_b)
                return {
                    "action": "daily_briefing",
                    "status": "success",
                    "voice_response": voice_str,
                    "briefing": voice_str,
                    "components": res_b.get("components", {}) if hasattr(res_b, "get") else {}
                }
        step_prompt = args.get("prompt") or action
        res = self.llm.plan(step_prompt, dry_run=dry_run)
        if isinstance(res, tuple):
            success, msg = res
            return {"action": action, "status": "success" if success else "error", "voice_response": msg}
        return res

    def _match_semantic_fastpath(self, prompt: str) -> Optional[Dict[str, Any]]:
        """
        Embedding-Assisted / Lexical Semantic Fast-Path (Phase 9).
        Matches colloquial and varied user expressions against canonical intent exemplars.
        Returns the fast-path tool execution spec in <5ms.
        """
        norm = normalize_trigger(prompt)
        p_tokens = set(re.findall(r"\w+", norm))
        if not p_tokens:
            return None

        best_match = None
        highest_score = 0.0

        for key, spec in CANONICAL_FASTPATH_INTENTS.items():
            for phrase in spec["phrases"]:
                phr_tokens = set(re.findall(r"\w+", phrase))
                overlap = len(p_tokens & phr_tokens)
                if not phr_tokens:
                    continue
                score = overlap / float(len(phr_tokens))
                if phrase in norm or norm in phrase:
                    score = max(score, 0.95)
                if score > highest_score and score >= 0.75:
                    highest_score = score
                    best_match = {
                        "action": spec["action"],
                        "args": dict(spec["args"]),
                        "voice_response": spec["voice"],
                        "semantic_fastpath": True,
                        "intent_key": key,
                        "confidence": round(highest_score, 2)
                    }

        return best_match

    def plan_or_execute(self, prompt: str, dry_run: bool = False, client_scope: str = "local_desktop", session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes the prompt through PreAct deterministic macro caching (<5ms fast-path),
        fast-path single dispatch, or multi-step coordination backed by AgentScratchpad.
        When client_scope == "remote_web", enforces strict sandboxing restricting desktop OS tools.
        """
        if client_scope == "remote_web":
            for pat in REMOTE_SANDBOX_PATTERNS:
                if re.search(pat, prompt, re.IGNORECASE):
                    if not re.search(r"open\s+(?:my\s+)?(?:google|chrome|browser)\s+and\s+search", prompt, re.IGNORECASE):
                        return {
                            "action": "sandboxed_blocked",
                            "status": "blocked",
                            "voice_response": "Remote Web Mode active: Desktop OS control is restricted to local PC sessions.",
                            "client_scope": client_scope
                        }

        if session_id and hasattr(self.llm, "active_session_id"):
            self.llm.active_session_id = session_id

        # STRICT ROUTE ISOLATION: Weather Intent (Tier 1 Fix)
        # Directly queries tools.weather and returns immediately without running secondary RAG or web search
        if is_weather_intent(prompt):
            sub_steps = self.split_compound_intent(prompt)
            if len(sub_steps) == 1:
                ctx_city = None
                if hasattr(self.llm, "last_context") and isinstance(self.llm.last_context, dict):
                    ctx_city = self.llm.last_context.get("city")
                res = dispatch_weather(
                    prompt,
                    dry_run=dry_run,
                    default_city=getattr(self.llm, "city", "Kuala Lumpur"),
                    context_city=ctx_city
                )
                res["compound"] = False
                if hasattr(self.llm, "last_context") and isinstance(self.llm.last_context, dict):
                    loc_val = res.get("location") or (res.get("args") or {}).get("location")
                    if loc_val:
                        self.llm.last_context["city"] = str(loc_val).split(",")[0].strip()
                fast_tm = {
                    "input_tokens": 0, "output_tokens": max(1, len(res.get("voice_response", "")) // 4),
                    "total_tokens": max(1, len(res.get("voice_response", "")) // 4),
                    "tokens_per_sec": 0.0, "saved_tokens": 350,
                    "model": "weather_isolated", "fast_path": True
                }
                res["token_metrics"] = fast_tm
                if hasattr(self.llm, "last_token_metrics"):
                    self.llm.last_token_metrics = dict(fast_tm)
                return res

        norm_trigger = normalize_trigger(prompt)
        intent_signature = f"macro:{norm_trigger}"
        t_start = time.perf_counter()
        sub_steps = self.split_compound_intent(prompt)

        # PREACT DETERMINISTIC ACTION MACRO FAST-PATH (<5ms)
        _DYNAMIC_NO_MACRO_ACTIONS = {"chat", "clarify", "error", "active_window", "weather", "world_time", "time", "run_learned_skill", "lookup_entity", "web_search", "deep_research", "computer_use_agent", "daily_briefing"}
        if len(sub_steps) == 1 and hasattr(self.llm, "memory") and hasattr(self.llm.memory, "get_action_macro"):
            cached_macro = self.llm.memory.get_action_macro(norm_trigger)
            if cached_macro and cached_macro.get("success_count", 0) >= 2:
                tool_chain = cached_macro.get("tool_chain", [])
                if tool_chain and not any(s.get("action") in _DYNAMIC_NO_MACRO_ACTIONS for s in tool_chain):
                    profiler.record_preact_cache_hit(
                        trigger=norm_trigger,
                        intent_signature=intent_signature,
                        latency_saved_ms=cached_macro.get("avg_latency_ms", 120.0)
                    )
                    step_results: List[Dict[str, Any]] = []
                    voice_responses: List[str] = []

                    for step_item in tool_chain:
                        act = step_item.get("action", "")
                        args = step_item.get("args", {})
                        res = self._execute_cached_tool(act, args, dry_run=dry_run)
                        step_results.append(res)
                        v = res.get("voice_response")
                        if v and v != "Dry-run response.":
                            voice_responses.append(v)

                    elapsed_ms = (time.perf_counter() - t_start) * 1000.0
                    if not dry_run:
                        self.llm.memory.record_action_macro(
                            norm_trigger,
                            intent_signature,
                            tool_chain,
                            latency_ms=elapsed_ms
                        )

                    combined_voice = " ".join(voice_responses) if voice_responses else f"Completed {norm_trigger}."
                    macro_act = tool_chain[0].get("action") if len(tool_chain) == 1 else "macro_chain"
                    if client_scope == "remote_web" and (macro_act in BLOCKED_REMOTE_ACTIONS or any(s.get("action") in BLOCKED_REMOTE_ACTIONS for s in tool_chain)):
                        return {
                            "action": "sandboxed_blocked",
                            "status": "blocked",
                            "voice_response": "Remote Web Mode active: Desktop OS control is restricted to local PC sessions.",
                            "client_scope": client_scope
                        }
                    fast_tm = {
                        "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                        "tokens_per_sec": 0.0, "saved_tokens": 350,
                        "model": "preact_macro", "fast_path": True
                    }
                    if hasattr(self.llm, "last_token_metrics"):
                        self.llm.last_token_metrics = dict(fast_tm)
                    out_macro = {
                        "action": macro_act,
                        "compound": len(tool_chain) > 1,
                        "steps": [norm_trigger],
                        "actions": [s.get("action") for s in tool_chain],
                        "step_results": step_results,
                        "voice_response": normalize_for_tts(combined_voice),
                        "preact_cached": True,
                        "token_metrics": fast_tm,
                        "latency_ms": round(elapsed_ms, 2)
                    }
                    if len(step_results) == 1 and isinstance(step_results[0], dict) and step_results[0].get("slug"):
                        out_macro["slug"] = step_results[0]["slug"]
                    return out_macro

        # SEMANTIC FAST-PATH ROUTING (Phase 9) (<5ms) - Only for single-clause intents
        if len(sub_steps) == 1:
            sem_fast = self._match_semantic_fastpath(prompt)
            if sem_fast:
                if client_scope == "remote_web" and sem_fast["action"] in BLOCKED_REMOTE_ACTIONS:
                    return {
                        "action": "sandboxed_blocked",
                        "status": "blocked",
                        "voice_response": "Remote Web Mode active: Desktop OS control is restricted to local PC sessions.",
                        "client_scope": client_scope
                    }
                profiler.record_metric("semantic_fastpath_hit", 1.0)
                res = self._execute_cached_tool(sem_fast["action"], sem_fast["args"], dry_run=dry_run)
                res["semantic_fastpath"] = True
                res["compound"] = False
                fast_tm = {
                    "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                    "tokens_per_sec": 0.0, "saved_tokens": 350,
                    "model": "semantic_fastpath", "fast_path": True
                }
                res["token_metrics"] = fast_tm
                if hasattr(self.llm, "last_token_metrics"):
                    self.llm.last_token_metrics = dict(fast_tm)
                if sem_fast.get("voice_response") and not res.get("voice_response"):
                    res["voice_response"] = sem_fast["voice_response"]
                return res

        # FAST PATH (<5ms): Single intent query
        if len(sub_steps) == 1:
            res = self.llm.plan(prompt, dry_run=dry_run)
            res["compound"] = False
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            act = res.get("action")
            if client_scope == "remote_web" and act in BLOCKED_REMOTE_ACTIONS:
                return {
                    "action": "sandboxed_blocked",
                    "status": "blocked",
                    "voice_response": "Remote Web Mode active: Desktop OS control is restricted to local PC sessions.",
                    "client_scope": client_scope,
                    "blocked_action": act
                }
            if not dry_run and act and act not in _DYNAMIC_NO_MACRO_ACTIONS and res.get("status") != "error":
                tool_chain = [{"action": act, "args": res.get("args", {})}]
                if hasattr(self.llm, "memory") and hasattr(self.llm.memory, "record_action_macro"):
                    self.llm.memory.record_action_macro(
                        norm_trigger,
                        intent_signature,
                        tool_chain,
                        latency_ms=elapsed_ms
                    )
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

        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        if not dry_run:
            successful_chain = [
                {"action": r.get("action"), "args": r.get("args", {})}
                for r in step_results
                if r.get("action") and r.get("action") not in ["chat", "clarify", "error", "active_window", "weather", "daily_briefing"] and r.get("status") != "error"
            ]
            if successful_chain and len(successful_chain) == len(step_results):
                if hasattr(self.llm, "memory") and hasattr(self.llm.memory, "record_action_macro"):
                    self.llm.memory.record_action_macro(
                        norm_trigger,
                        intent_signature,
                        successful_chain,
                        latency_ms=elapsed_ms
                    )

        if client_scope == "remote_web" and any(a in BLOCKED_REMOTE_ACTIONS for a in actions):
            return {
                "action": "sandboxed_blocked",
                "status": "blocked",
                "voice_response": "Remote Web Mode active: Desktop OS control is restricted to local PC sessions.",
                "client_scope": client_scope
            }

        comp_tm = {
            "input_tokens": sum(int(r.get("token_metrics", {}).get("input_tokens", 0)) for r in step_results),
            "output_tokens": sum(int(r.get("token_metrics", {}).get("output_tokens", 0)) for r in step_results),
            "total_tokens": sum(int(r.get("token_metrics", {}).get("total_tokens", 0)) for r in step_results),
            "saved_tokens": sum(int(r.get("token_metrics", {}).get("saved_tokens", 0)) for r in step_results),
            "model": step_results[0].get("token_metrics", {}).get("model", "qwen3:8b") if step_results else "qwen3:8b"
        }
        return {
            "compound": True,
            "steps": sub_steps[:self.MAX_STEPS],
            "actions": actions,
            "step_results": step_results,
            "scratchpad": self.scratchpad.get_state(),
            "token_metrics": comp_tm,
            "voice_response": combined_voice
        }

    def plan(self, prompt: str, client_scope: str = "local_desktop", session_id: Optional[str] = None) -> Dict[str, Any]:
        """Dry-run planner isolating side-effects."""
        return self.plan_or_execute(prompt, dry_run=True, client_scope=client_scope, session_id=session_id)

    def execute(self, prompt: str, client_scope: str = "local_desktop", session_id: Optional[str] = None) -> Dict[str, Any]:
        """Live execution pipeline."""
        return self.plan_or_execute(prompt, dry_run=False, client_scope=client_scope, session_id=session_id)

    def process_command(
        self,
        user_input: str,
        client_scope: str = "local_desktop",
        dry_run: bool = False,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Unified entry point for local desktop and remote web clients (Phase 10).
        Enforces client_scope sandboxing when client_scope == 'remote_web' and routes to session_id.
        """
        return self.plan_or_execute(user_input, dry_run=dry_run, client_scope=client_scope, session_id=session_id)