import os
import re
from typing import Dict, Any, Tuple, Optional, List, Callable

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

NOISE_WORDS = {
    "please", "can", "you", "could", "would", "tell", "me", "about",
    "search", "for", "find", "look", "up", "what", "is", "are", "the",
    "exact", "specific", "right", "now", "currently", "hey", "libra",
    "do", "know", "give", "some", "information", "details", "on", "in",
    "a", "an", "of", "to", "and", "or", "with", "regarding", "concerning"
}


class ExecutionRefiner:
    """
    Self-Refine & Output Critique Loop for Project Libra v6.0.
    Validates tool execution outputs, detects empty/error states,
    reformulates overly noisy web search queries, and runs fuzzy condensed
    file matching before returning failure.
    """

    def __init__(self, file_mgr: Optional[Any] = None):
        self.file_mgr = file_mgr

    def evaluate_tool_output(self, action: str, result: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Inspects tool output for failure states:
          - Empty web search results (0 sources)
          - status == 'not_found' / 'error' / 'failed'
          - HTTP 429 / 500 status codes
          - Empty text extractions
        Returns (is_valid, critique_reason).
        """
        if not result or not isinstance(result, dict):
            return False, "Tool returned empty or non-dictionary output."

        # 1. Check HTTP status errors (429 / 500+)
        http_code = result.get("http_status") or result.get("status_code")
        if isinstance(http_code, int) and http_code in (429, 500, 502, 503, 504):
            return False, f"HTTP {http_code} error encountered."

        err_text = str(result.get("error") or result.get("message") or "")
        if re.search(r"\bHTTP\s*(?:429|50\d)\b", err_text, re.IGNORECASE):
            return False, f"HTTP error detected in response: {err_text}"

        # 2. Check explicit status field
        status = str(result.get("status", "")).lower().strip()
        if status in ("not_found", "error", "failed", "http_error", "empty"):
            return False, f"Tool reported failure status: '{status}'."

        # 3. Check web_search / research source count
        act_lower = (action or "").lower().strip()
        if act_lower in ("web_search", "research", "execute_research"):
            sources = result.get("sources")
            if isinstance(sources, list) and len(sources) == 0:
                return False, "Web search returned 0 sources."
            voice = str(result.get("voice_response") or "").lower()
            if "found no verified" in voice or "no results found" in voice:
                return False, "Web search yielded no verified results."

        # 4. Check document / text extraction completeness
        if act_lower in ("document_rag", "extract_text", "read_file"):
            if "text" in result and not str(result.get("text") or "").strip():
                return False, "Extracted text content is empty."
            if "answer" in result and not str(result.get("answer") or "").strip():
                return False, "Document RAG produced an empty answer."

        return True, "Output verified."

    def reformulate_query(self, query: str) -> str:
        """
        Strips conversational filler, punctuation, and overly restrictive modifiers
        to produce a clean, high-recall search query.
        """
        if not query:
            return ""

        # Remove punctuation and quotes
        cleaned = re.sub(r"[^\w\s\-\.]", " ", query)
        tokens = cleaned.split()

        kept_tokens = [
            t for t in tokens
            if t.lower().strip(".") not in NOISE_WORDS and len(t.strip(".")) > 1
        ]

        if not kept_tokens:
            # Fallback to alphanumeric words from original query
            return re.sub(r"[^\w\s]", "", query).strip()

        return " ".join(kept_tokens)

    def fuzzy_file_search(
        self,
        query: str,
        search_dirs: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Performs condensed fuzzy matching (ignoring spaces, hyphens, underscores, case)
        across candidate directories when exact file/folder lookup fails.
        """
        if not query:
            return None

        norm_target = re.sub(r"[\s_\-]+", "", query.lower()).strip()
        if not norm_target:
            return None

        dirs_to_scan: List[str] = list(search_dirs or [])
        if not dirs_to_scan:
            home = os.path.expanduser("~")
            for sub in ("Desktop", "Documents", "Downloads"):
                p = os.path.join(home, sub)
                if os.path.isdir(p):
                    dirs_to_scan.append(p)
            dirs_to_scan.append(PROJECT_ROOT)

        for d in dirs_to_scan:
            if not os.path.isdir(d):
                continue
            try:
                for entry in os.listdir(d):
                    norm_entry = re.sub(r"[\s_\-]+", "", entry.lower())
                    norm_stem = re.sub(r"[\s_\-]+", "", os.path.splitext(entry)[0].lower())
                    if (
                        norm_target == norm_entry
                        or norm_target == norm_stem
                        or norm_target in norm_entry
                        or (len(norm_stem) >= 3 and norm_stem in norm_target)
                    ):
                        return os.path.join(d, entry)
            except Exception:
                continue

        return None

    def refine_and_retry(
        self,
        action: str,
        query: str,
        initial_result: Dict[str, Any],
        retry_callback: Optional[Callable[[str], Dict[str, Any]]] = None,
        search_dirs: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Critiques initial_result. If valid, returns it untouched.
        If invalid, automatically reformulates the query (or performs fuzzy file lookup)
        and executes a single retry.
        """
        is_valid, reason = self.evaluate_tool_output(action, initial_result)
        if is_valid:
            out = dict(initial_result)
            out.setdefault("refined", False)
            return out

        act_lower = (action or "").lower().strip()

        # 1. Web Search Reformulation & Automatic Retry
        if act_lower in ("web_search", "research", "execute_research"):
            broad_query = self.reformulate_query(query)
            if callable(retry_callback) and broad_query:
                retry_res = dict(retry_callback(broad_query) or {})
                retry_ok, _ = self.evaluate_tool_output(action, retry_res)
                retry_res["refined"] = True
                retry_res["original_query"] = query
                retry_res["reformulated_query"] = broad_query
                retry_res["critique_reason"] = reason
                retry_res["retry_succeeded"] = retry_ok
                return retry_res

        # 2. File / Folder Fuzzy Condensed Fallback
        if act_lower in ("file_search", "open_folder", "document_rag", "open_file"):
            matched_path = self.fuzzy_file_search(query, search_dirs=search_dirs)
            if matched_path:
                name = os.path.basename(matched_path)
                return {
                    "action": action,
                    "status": "opened" if act_lower == "open_folder" else "found",
                    "path": matched_path,
                    "folder": name,
                    "file": matched_path,
                    "refined": True,
                    "original_query": query,
                    "reformulated_query": name,
                    "critique_reason": reason,
                    "retry_succeeded": True,
                    "voice_response": f"Opened {name}."
                }

            condensed_q = re.sub(r"[\s_\-]+", "", query).strip()
            if callable(retry_callback) and condensed_q and condensed_q != query:
                retry_res = dict(retry_callback(condensed_q) or {})
                retry_ok, _ = self.evaluate_tool_output(action, retry_res)
                retry_res["refined"] = True
                retry_res["original_query"] = query
                retry_res["reformulated_query"] = condensed_q
                retry_res["critique_reason"] = reason
                retry_res["retry_succeeded"] = retry_ok
                return retry_res

        failed_out = dict(initial_result or {})
        failed_out["refined"] = False
        failed_out["critique_reason"] = reason
        return failed_out
