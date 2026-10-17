import re
from typing import List, Dict, Any, Optional, Callable


class AgentScratchpad:
    """
    Ephemeral Agent Scratchpad & Multi-Step Planner for Project Libra v6.0.
    Manages an in-memory execution graph for compound or complex tasks,
    evaluates intermediate step success via self-reflection, proposes fallback
    subtasks on failure, and compresses technical state into natural spoken updates.
    """

    MAX_SUBTASKS: int = 4

    def __init__(self, goal: str = "", subtasks: Optional[List[Dict[str, Any]]] = None):
        self.goal: str = goal
        self.subtasks: List[Dict[str, Any]] = []
        self.reflection_notes: List[str] = []
        self.current_step: int = 0
        if goal or subtasks:
            self.init_plan(goal, subtasks or [])

    def reset(self):
        """Clears the current scratchpad state."""
        self.goal = ""
        self.subtasks = []
        self.reflection_notes = []
        self.current_step = 0

    def init_plan(self, goal: str, subtasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Initializes a new multi-step execution plan capped at MAX_SUBTASKS (4).
        Each subtask contains: id, action, args, status ('pending'|'running'|'completed'|'failed'), result.
        """
        self.goal = (goal or "").strip()
        self.reflection_notes = []
        self.current_step = 0
        self.subtasks = []

        capped_inputs = list(subtasks or [])[:self.MAX_SUBTASKS]
        for idx, item in enumerate(capped_inputs):
            action = item.get("action") or item.get("prompt") or "execute_step"
            args = item.get("args") if isinstance(item.get("args"), dict) else {}
            if "prompt" in item and "prompt" not in args:
                args["prompt"] = item["prompt"]
            self.subtasks.append({
                "id": item.get("id", idx + 1),
                "action": action,
                "args": args,
                "status": item.get("status", "pending"),
                "result": item.get("result", None)
            })

        if len(subtasks or []) > self.MAX_SUBTASKS:
            self.reflection_notes.append(
                f"Loop guard triggered: truncated {len(subtasks)} requested subtasks to maximum {self.MAX_SUBTASKS}."
            )

        return self.get_state()

    def add_subtask(self, action: str, args: Optional[Dict[str, Any]] = None) -> bool:
        """Appends a subtask if within the 4-step safety cap."""
        if len(self.subtasks) >= self.MAX_SUBTASKS:
            self.reflection_notes.append(
                f"Cannot append subtask '{action}': MAX_SUBTASKS ({self.MAX_SUBTASKS}) reached."
            )
            return False

        self.subtasks.append({
            "id": len(self.subtasks) + 1,
            "action": action,
            "args": args or {},
            "status": "pending",
            "result": None
        })
        return True

    def reflect_and_plan(self, step_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates whether the current subtask succeeded.
        If a subtask failed (e.g. file not found, empty search, status == 'failed'/'error'/'not_found'),
        logs a reflection note and proposes an alternate subtask before aborting.
        """
        res = step_result or {}
        if self.current_step < len(self.subtasks):
            current_task = self.subtasks[self.current_step]
        else:
            current_task = {
                "id": self.current_step + 1,
                "action": res.get("action", "unknown"),
                "args": res.get("args", {}),
                "status": "running",
                "result": None
            }

        status_val = str(res.get("status", "success")).lower()
        action_name = current_task.get("action") or res.get("action", "step")
        sources = res.get("sources")

        # Determine if step failed
        failed = False
        failure_reason = ""
        if status_val in ["failed", "error", "not_found", "http_error", "empty"]:
            failed = True
            failure_reason = f"status='{status_val}'"
        elif action_name in ["web_search", "research"] and isinstance(sources, list) and len(sources) == 0:
            failed = True
            failure_reason = "0 web sources returned"
        elif res.get("error"):
            failed = True
            failure_reason = str(res.get("error"))

        alternate_subtask: Optional[Dict[str, Any]] = None
        reflection_note: Optional[str] = None

        if failed:
            current_task["status"] = "failed"
            current_task["result"] = res

            # Propose an alternate fallback subtask
            orig_args = dict(current_task.get("args") or {})
            if action_name in ["open_folder", "file_search", "document_rag"]:
                target_q = orig_args.get("folder") or orig_args.get("query") or orig_args.get("file") or res.get("folder") or "target"
                fuzzy_q = re.sub(r"[\s_\-]+", "", str(target_q)).lower()
                alternate_subtask = {
                    "id": len(self.subtasks) + 1,
                    "action": "fuzzy_file_search",
                    "args": {"query": fuzzy_q, "fallback_from": action_name},
                    "status": "pending",
                    "result": None
                }
                reflection_note = (
                    f"Step {current_task['id']} ({action_name}) failed ({failure_reason}). "
                    f"Proposed alternate fuzzy search for '{fuzzy_q}'."
                )
            elif action_name in ["web_search", "research"]:
                orig_q = orig_args.get("query") or res.get("query") or self.goal
                broad_q = re.sub(r"\b(please|exact|specific|latest|right now|can you|find)\b", "", str(orig_q), flags=re.IGNORECASE).strip()
                alternate_subtask = {
                    "id": len(self.subtasks) + 1,
                    "action": "web_search",
                    "args": {"query": broad_q or orig_q, "retry": True},
                    "status": "pending",
                    "result": None
                }
                reflection_note = (
                    f"Step {current_task['id']} ({action_name}) returned empty results. "
                    f"Proposed broader query reformulation: '{broad_q}'."
                )
            else:
                alternate_subtask = {
                    "id": len(self.subtasks) + 1,
                    "action": "fallback_recovery",
                    "args": {"original_action": action_name, "original_args": orig_args},
                    "status": "pending",
                    "result": None
                }
                reflection_note = (
                    f"Step {current_task['id']} ({action_name}) encountered failure ({failure_reason}). "
                    f"Proposed fallback recovery subtask."
                )

            self.reflection_notes.append(reflection_note)
        else:
            current_task["status"] = "completed"
            current_task["result"] = res

        self.current_step += 1

        return {
            "step_succeeded": not failed,
            "status": current_task["status"],
            "reflection_note": reflection_note,
            "alternate_subtask": alternate_subtask,
            "current_step": self.current_step,
            "completed": self.current_step >= len(self.subtasks)
        }

    def execute_graph(
        self,
        executor_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        auto_insert_alternate: bool = False
    ) -> Dict[str, Any]:
        """
        Executes all subtasks sequentially up to MAX_SUBTASKS (4), running reflect_and_plan
        after each step and returning the final graph state and spoken summary.
        """
        idx = 0
        while idx < len(self.subtasks) and idx < self.MAX_SUBTASKS:
            task = self.subtasks[idx]
            self.current_step = idx
            task["status"] = "running"

            step_res = executor_fn(task)
            reflection = self.reflect_and_plan(step_res)

            if not reflection["step_succeeded"] and auto_insert_alternate:
                alt = reflection.get("alternate_subtask")
                if alt and len(self.subtasks) < self.MAX_SUBTASKS:
                    self.subtasks.append(alt)

            idx += 1

        return {
            "goal": self.goal,
            "subtasks": self.subtasks,
            "reflection_notes": self.reflection_notes,
            "steps_executed": idx,
            "spoken_summary": self.compress_for_speech()
        }

    def compress_for_speech(self) -> str:
        """
        Translates internal scratchpad states into clean, concise spoken progress updates
        without reading technical data, file paths, or raw dictionaries aloud.
        """
        if not self.subtasks:
            return "Ready."

        completed_voices: List[str] = []
        completed_actions: List[str] = []
        failed_count = 0

        for task in self.subtasks:
            status = task.get("status")
            res = task.get("result") or {}
            action = str(task.get("action", "step")).replace("_", " ")

            if status == "completed":
                voice = (res.get("voice_response") or "").strip()
                if voice and voice != "Dry-run response.":
                    # Strip raw paths or technical brackets for clean speech
                    clean_v = re.sub(r"[A-Za-z]:\\[^\s]+", "the requested location", voice)
                    clean_v = re.sub(r"\{.*?\}", "", clean_v).strip()
                    if clean_v:
                        completed_voices.append(clean_v)
                completed_actions.append(action)
            elif status == "failed":
                failed_count += 1

        if completed_voices:
            combined = " ".join(completed_voices)
            return combined

        if completed_actions and failed_count == 0:
            return f"Completed {len(completed_actions)} steps: {', '.join(completed_actions)}."
        elif completed_actions and failed_count > 0:
            return f"Completed {len(completed_actions)} steps, with {failed_count} step requiring fallback adjustment."
        elif failed_count > 0:
            return "I encountered an issue completing that task and logged a recovery note."

        return f"Working on {self.goal or 'your request'}."

    def get_spoken_summary(self) -> str:
        """Alias for compress_for_speech."""
        return self.compress_for_speech()

    def get_state(self) -> Dict[str, Any]:
        """Returns a serializable snapshot of the scratchpad state."""
        return {
            "goal": self.goal,
            "subtasks": list(self.subtasks),
            "reflection_notes": list(self.reflection_notes),
            "current_step": self.current_step,
            "spoken_summary": self.compress_for_speech()
        }
